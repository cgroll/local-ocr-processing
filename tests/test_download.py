import hashlib

import pymupdf
import pytest

from conftest import entry, make_pdf
from docparse.dataset import download, manifest


def run(entries, server, tmp_path, **kw):
    kw.setdefault("min_interval", 0)
    return download.download_all(entries, raw_root=tmp_path / "raw", cache_dir=tmp_path / "cache", **kw)


# 2.1 fetch: valid PDF, HTML error page, oversized file

def test_valid_pdf_is_stored_in_own_directory(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf")
    [out] = run([e], server, tmp_path)
    assert out.status == "downloaded", out.message
    pdf = tmp_path / "raw" / "doc-a" / "document.pdf"
    assert pdf.read_bytes() == server.ok_pdf
    assert not list(pdf.parent.glob("*.part"))


def test_html_error_page_is_rejected_and_leaves_no_file(server, tmp_path):
    [out] = run([entry("doc-h", f"{server.base}/error.html")], server, tmp_path)
    assert out.status == "error" and "not a PDF" in out.message
    assert list((tmp_path / "raw" / "doc-h").iterdir()) == []


def test_oversized_file_is_rejected(server, tmp_path):
    [out] = run([entry("doc-b", f"{server.base}/big.pdf")], server, tmp_path, max_bytes=1024 * 1024)
    assert out.status == "error" and "too large" in out.message
    assert list((tmp_path / "raw" / "doc-b").iterdir()) == []


def test_http_error_is_reported_per_entry_and_run_continues(server, tmp_path):
    entries = [entry("doc-m", f"{server.base}/missing"), entry("doc-a", f"{server.base}/ok.pdf")]
    outs = run(entries, server, tmp_path)
    assert [o.status for o in outs] == ["error", "downloaded"]


# 2.2 per-host pacing

def test_requests_to_same_host_keep_minimum_interval(server, tmp_path):
    entries = [entry("a", f"{server.base}/ok.pdf"), entry("b", f"{server.base}/ok2.pdf")]
    run(entries, server, tmp_path, min_interval=0.4)
    t = [ts for _, ts in server.requests]
    assert len(t) == 2 and t[1] - t[0] >= 0.35


def test_user_agent_is_identifiable():
    assert "docparse" in download.USER_AGENT


# 2.3 verification and first ingest

def test_first_ingest_fills_hash_pages_and_kind(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf")
    run([e], server, tmp_path)
    assert e.sha256 == hashlib.sha256(server.ok_pdf).hexdigest()
    assert e.pages == "2" and e.kind == "native" and e.page_range == ""


def test_hash_mismatch_is_error_and_file_is_withheld(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf", sha256="0" * 64)
    [out] = run([e], server, tmp_path)
    assert out.status == "error" and "sha256 mismatch" in out.message
    d = tmp_path / "raw" / "doc-a"
    assert not (d / "document.pdf").exists() and (d / "document.pdf.rejected").exists()
    assert e.sha256 == "0" * 64


def test_page_count_mismatch_is_error(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf", pages="7")
    [out] = run([e], server, tmp_path)
    assert out.status == "error" and "page count mismatch" in out.message


def test_manual_placement_is_verified_without_download(server, tmp_path):
    d = tmp_path / "raw" / "doc-a"
    d.mkdir(parents=True)
    (d / "document.pdf").write_bytes(make_pdf(4))
    e = entry("doc-a", f"{server.base}/missing")
    [out] = run([e], server, tmp_path)
    assert out.status == "skipped" and e.pages == "4" and e.sha256
    assert server.requests == []


# 2.4 idempotence

def test_second_run_skips_everything_without_requests(server, tmp_path):
    entries = [entry("a", f"{server.base}/ok.pdf"), entry("b", f"{server.base}/ok2.pdf")]
    run(entries, server, tmp_path)
    server.requests.clear()
    outs = run(entries, server, tmp_path)
    assert [o.status for o in outs] == ["skipped", "skipped"]
    assert server.requests == []


def test_local_file_differing_from_manifest_hash_is_error(server, tmp_path):
    e = entry("a", f"{server.base}/ok.pdf")
    run([e], server, tmp_path)
    (tmp_path / "raw" / "a" / "document.pdf").write_bytes(make_pdf(5))
    [out] = run([e], server, tmp_path)
    assert out.status == "error" and "does not match" in out.message


# 2.5 classification and page cap

def test_text_pdf_is_native(tmp_path):
    p = tmp_path / "t.pdf"
    p.write_bytes(make_pdf(3))
    with pymupdf.open(p) as doc:
        assert download.classify(doc, 1, 3) == "native"


def test_image_only_pdf_is_scanned(tmp_path):
    p = tmp_path / "s.pdf"
    p.write_bytes(make_pdf(3, text=False, scan=True))
    with pymupdf.open(p) as doc:
        assert download.classify(doc, 1, 3) == "scanned"


def test_scan_with_hidden_text_layer_still_counts_as_scanned(tmp_path):
    p = tmp_path / "s.pdf"
    p.write_bytes(make_pdf(3, text=True, scan=True))
    with pymupdf.open(p) as doc:
        assert download.classify(doc, 1, 3) == "scanned"


def test_half_text_half_scan_is_mixed(tmp_path):
    a, b = pymupdf.open(), pymupdf.open()
    a.insert_pdf(pymupdf.open("pdf", make_pdf(2)))
    a.insert_pdf(pymupdf.open("pdf", make_pdf(2, text=False, scan=True)))
    p = tmp_path / "m.pdf"
    a.save(p)
    with pymupdf.open(p) as doc:
        assert download.classify(doc, 1, 4) == "mixed"


def test_long_document_gets_page_range_cap(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok2.pdf")  # 3 pages
    run([e], server, tmp_path, max_pages=2)
    assert e.pages == "3" and e.page_range == "1-2" and e.page_count == 2


def test_manual_kind_is_not_overwritten(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf", kind="mixed")
    run([e], server, tmp_path)
    assert e.kind == "mixed"


def test_manifest_stays_valid_after_ingest(server, tmp_path):
    e = entry("doc-a", f"{server.base}/ok.pdf")
    run([e], server, tmp_path)
    assert manifest.validate([e], require_verified=True) == []


# 2.6 zip entries

def zip_entry(server, id, member):
    return entry(id, f"{server.base}/pack.zip#{member}", group="corpus-sample")


def test_two_entries_from_one_zip_need_one_zip_request_and_zip_is_deleted(server, tmp_path):
    entries = [zip_entry(server, "a", "000/000001.pdf"), zip_entry(server, "b", "000/000002.pdf")]
    outs = run(entries, server, tmp_path)
    assert [o.status for o in outs] == ["downloaded", "downloaded"], outs
    assert [p for p, _ in server.requests] == ["/pack.zip"]
    assert (tmp_path / "raw" / "a" / "document.pdf").read_bytes() == server.ok_pdf
    assert entries[1].pages == "3"
    assert list((tmp_path / "cache").iterdir()) == []


def test_missing_non_pdf_and_oversized_entries_fail_individually(server, tmp_path):
    entries = [
        zip_entry(server, "gone", "000/nope.pdf"), zip_entry(server, "txt", "000/000003.txt"),
        zip_entry(server, "big", "000/000004.pdf"), zip_entry(server, "ok", "000/000001.pdf"),
    ]
    outs = {o.id: o for o in run(entries, server, tmp_path, max_bytes=1024 * 1024)}
    assert "not in" in outs["gone"].message and "not a PDF" in outs["txt"].message
    assert "too large" in outs["big"].message and outs["ok"].status == "downloaded"
    assert list((tmp_path / "raw" / "big").iterdir()) == []


def test_second_run_does_not_fetch_the_zip_again(server, tmp_path):
    entries = [zip_entry(server, "a", "000/000001.pdf")]
    run(entries, server, tmp_path)
    server.requests.clear()
    assert [o.status for o in run(entries, server, tmp_path)] == ["skipped"]
    assert server.requests == []


def test_broken_zip_is_an_error_and_not_kept_in_cache(server, tmp_path):
    e = entry("a", f"{server.base}/bad.zip#x.pdf")
    [out] = run([e], server, tmp_path)
    assert out.status == "error" and "bad zip" in out.message
    assert list((tmp_path / "cache").glob("*")) == []


def test_zip_download_respects_zip_size_limit(server, tmp_path):
    [out] = run([zip_entry(server, "a", "000/000001.pdf")], server, tmp_path, max_zip_bytes=1000)
    assert out.status == "error" and "too large" in out.message


def test_entry_name_never_escapes_the_raw_directory(server, tmp_path):
    [out] = run([entry("a", f"{server.base}/pack.zip#../../evil.pdf")], server, tmp_path)
    assert out.status == "error"
    assert not (tmp_path / "evil.pdf").exists()
