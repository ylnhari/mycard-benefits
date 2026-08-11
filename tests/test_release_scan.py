from __future__ import annotations

import base64
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "release_scan.py"
SPEC = importlib.util.spec_from_file_location("release_scan", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
release_scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_scan
SPEC.loader.exec_module(release_scan)

CANDIDATE_SCRIPT_PATH = ROOT / "scripts" / "release_candidate_check.py"
CANDIDATE_SPEC = importlib.util.spec_from_file_location("release_candidate_check", CANDIDATE_SCRIPT_PATH)
assert CANDIDATE_SPEC is not None and CANDIDATE_SPEC.loader is not None
release_candidate_check = importlib.util.module_from_spec(CANDIDATE_SPEC)
sys.modules[CANDIDATE_SPEC.name] = release_candidate_check
CANDIDATE_SPEC.loader.exec_module(release_candidate_check)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "synthetic-release-repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "synthetic@example.invalid")
    _git(repo, "config", "user.name", "Synthetic Only")
    (repo / ".gitignore").write_text("ignored-private.txt\n", encoding="utf-8")
    (repo / "public.txt").write_text("public catalog fixture\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "public.txt")
    _git(repo, "commit", "-m", "synthetic base")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_scan_uses_only_explicit_tracked_git_content_and_sanitizes_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "ignored-private.txt").write_text(
        "SYNTHETIC-ONLY-" + "PRIVATE-SHOULD-NEVER-BE-READ", encoding="utf-8"
    )
    (repo / "public.txt").write_text(
        "".join(
            part
            for part in ("api", '_key = "SYNTHETIC-ONLY-TRACKED-CREDENTIAL"\n')
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic tracked update")

    exit_code = release_scan.main(["--files", "public.txt"], repo=repo)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert '"credential_signature": 1' in output
    assert "public.txt" not in output
    assert "SYNTHETIC-ONLY-TRACKED-CREDENTIAL" not in output
    assert "SYNTHETIC-ONLY-" + "PRIVATE-SHOULD-NEVER-BE-READ" not in output
    assert str(repo) not in output


def test_range_scan_reads_only_added_or_modified_tracked_paths(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "new-public.txt").write_text("5" * 16 + "\n", encoding="utf-8")
    (repo / "ignored-private.txt").write_text(
        "".join(
            part for part in ("pass", 'word = "SYNTHETIC-ONLY-IGNORED"\n')
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "new-public.txt")
    _git(repo, "commit", "-m", "synthetic range")
    head = _git(repo, "rev-parse", "HEAD")

    report = release_scan.scan_git_range(repo, f"{base}..{head}")

    assert report.target_kind == "range"
    assert report.file_count == 1
    assert report.findings["long_numeric_identifier"] == 1
    assert report.findings["credential_signature"] == 0


def test_scan_distinguishes_https_urls_from_machine_paths(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.txt").write_text("https://example.invalid/public\n", encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic https")

    https_report = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert https_report.findings["absolute_machine_path"] == 0

    machine_path = "C" + chr(58) + "\\synthetic\\machine-path\n"
    (repo / "public.txt").write_text(machine_path, encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic absolute path")

    machine_report = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert machine_report.findings["absolute_machine_path"] == 1


def test_scan_rejects_absolute_or_untracked_paths_without_printing_them(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    with pytest.raises(release_scan.ReleaseScanError, match="file path is invalid"):
        release_scan.scan_tracked_files(repo, [str(repo / "public.txt")])
    with pytest.raises(release_scan.ReleaseScanError, match="not tracked"):
        release_scan.scan_tracked_files(repo, ["missing.txt"])


def test_scan_allows_value_free_configuration_examples_and_docs(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / ".env.example").write_text(
        "# Copy this file to the local " + "." + "env\nMYCARD_BENEFITS_PORT=\n", encoding="utf-8"
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "configuration.md").write_text(
        "Local configuration may use a repository " + "." + "env; never commit values.\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".env.example", "docs/configuration.md")
    _git(repo, "commit", "-m", "synthetic configuration documentation")

    example = release_scan.scan_tracked_files(repo, [".env.example"])
    docs = release_scan.scan_tracked_files(repo, ["docs/configuration.md"])

    assert example.findings["private_data_path"] == 0
    assert example.findings["credential_signature"] == 0
    assert docs.findings["private_data_path"] == 0


def _split_sources() -> list[str]:
    quote = chr(34)
    escaped_quote = chr(92) + quote
    return [
        "".join(
            (
                "key = ",
                quote + "api" + quote + " + " + quote + "_key = ",
                escaped_quote + "SYNTHETIC-ONLY-TWO-FRAGMENT" + escaped_quote + quote,
                "\n",
            )
        ),
        "".join(
            (
                "key = ",
                quote + "api" + quote + " + " + quote + "_key = " + quote,
                quote + "SYNTHETIC-ONLY-THREE-FRAGMENT" + quote,
                "\n",
            )
        ),
        "".join(
            (
                "key = ",
                quote + "a" + quote + " + " + quote + "pi" + quote,
                " + " + quote + "_key = " + quote,
                quote + "SYNTHETIC-ONLY-MANY-FRAGMENT" + quote,
                "\n",
            )
        ),
        "".join(
            (
                "key = ",
                quote + quote + ".join((" + quote + "api" + quote,
                ", " + quote + "_key = " + quote + ", ",
                quote + "SYNTHETIC-ONLY-JOINED-FRAGMENT" + quote,
                "))\n",
            )
        ),
    ]


@pytest.mark.parametrize(
    "split_source",
    _split_sources(),
    ids=("two-fragments", "three-fragments", "many-fragments", "constant-join"),
)
def test_scan_rejects_credential_bearing_examples_and_original_split_signatures(
    tmp_path: Path, split_source: str
) -> None:
    repo, _ = _repo(tmp_path)
    credential_key = "".join(("API", "_KEY"))
    credential_value = "SYNTHETIC-ONLY-EXAMPLE-CREDENTIAL"
    (repo / ".env.example").write_text(
        f'{credential_key} = "{credential_value}"\n', encoding="utf-8"
    )
    _git(repo, "add", ".env.example")
    _git(repo, "commit", "-m", "synthetic credential example")
    example = release_scan.scan_tracked_files(repo, [".env.example"])
    assert example.findings["credential_signature"] == 1

    # The original split source is assembled only in the temporary Git repo.
    (repo / "public.txt").write_text(split_source, encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic split credential")
    split = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert split.findings["credential_signature"] == 1


@pytest.mark.parametrize("separator", ["\\u00a0", "\\u200b", "\\u2060"])
def test_scan_rejects_escaped_and_unicode_separated_standalone_signatures(
    tmp_path: Path, separator: str
) -> None:
    repo, _ = _repo(tmp_path)
    quote = chr(34)
    escaped = chr(92) + "x5f"
    source = "value = " + quote + "api" + escaped + "key" + separator + "=" + separator
    source += "SYNTHETIC-ONLY-NORMALIZED-CREDENTIAL" + quote + "\n"
    (repo / "public.txt").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic normalized credential")
    report = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert report.findings["credential_signature"] == 1


def test_scan_keeps_near_miss_text_as_a_false_positive_control(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.txt").write_text(
        "The password policy is documented; API keys are never stored here.\n",
        encoding="utf-8",
    )
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic credential documentation")
    report = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert report.findings["credential_signature"] == 0


def test_scan_uses_python_ast_context_for_value_free_credential_names(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(
        "secret = load_secret()\npassphrase: str\n", encoding="utf-8"
    )
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic value-free credential names")
    safe = release_scan.scan_tracked_files(repo, ["public.py"])
    assert safe.findings["credential_signature"] == 0

    (repo / "public.py").write_text(
        'api_key = "SYNTHETIC-ONLY-CONCRETE-CREDENTIAL"\n', encoding="utf-8"
    )
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic concrete credential")
    unsafe = release_scan.scan_tracked_files(repo, ["public.py"])
    assert unsafe.findings["credential_signature"] == 1


def test_scan_allows_only_reviewed_value_free_private_path_contexts(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / ".dockerignore").write_text("." + "env\ndata\n", encoding="utf-8")
    _git(repo, "add", ".dockerignore")
    _git(repo, "commit", "-m", "synthetic ignore rules")
    safe = release_scan.scan_tracked_files(repo, [".dockerignore"])
    assert safe.findings["private_data_path"] == 0

    (repo / "public.txt").write_text("private" + "/vault.json\n", encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic private path")
    unsafe = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert unsafe.findings["private_data_path"] == 1


def test_scan_allows_typed_public_provenance_hash_but_rejects_other_long_numbers(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "mycard_benefits").mkdir()
    (repo / "src" / "mycard_benefits" / "candidates").mkdir()
    content_sha256 = "1234567890123abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabc"
    (repo / "src" / "mycard_benefits" / "candidates" / "provenance.py").write_text(
        f'content_sha256 = "{content_sha256}"\n', encoding="utf-8"
    )
    _git(repo, "add", "src/mycard_benefits/candidates/provenance.py")
    _git(repo, "commit", "-m", "synthetic public provenance hash")
    safe = release_scan.scan_tracked_files(
        repo, ["src/mycard_benefits/candidates/provenance.py"]
    )
    assert safe.findings["long_numeric_identifier"] == 0

    (repo / "public.txt").write_text("1234567890" + "12345\n", encoding="utf-8")
    _git(repo, "add", "public.txt")
    _git(repo, "commit", "-m", "synthetic long numeric identifier")
    unsafe = release_scan.scan_tracked_files(repo, ["public.txt"])
    assert unsafe.findings["long_numeric_identifier"] == 1


@pytest.mark.parametrize(
    "source",
    [
        'config.api_key = "SYNTHETIC-ONLY-ATTRIBUTE-CREDENTIAL"\n',
        'config.credentials.api_key = "SYNTHETIC-ONLY-NESTED-ATTRIBUTE"\n',
        'vault["api_key"] = "SYNTHETIC-ONLY-SUBSCRIPT-CREDENTIAL"\n',
        'vault["credentials"]["api_key"] = "SYNTHETIC-ONLY-NESTED-SUBSCRIPT"\n',
        'vault["api" + "_key"] = "SYNTHETIC-ONLY-CONSTANT-KEY"\n',
        'registry["credentials"]["access_token"] = "{}".format("SYNTHETIC-ONLY-NESTED-FORMAT")\n',
    ],
    ids=("attribute", "nested-attribute", "subscript", "nested-subscript", "constant-key", "nested-expression"),
)
def test_scanners_reject_attribute_and_constant_subscript_credentials(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic attribute and subscript credential")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


@pytest.mark.parametrize(
    "source",
    [
        'message = "api_key = \'SYNTHETIC-ONLY-UNRELATED-STRING\'"\n',
        'message = "prefix " + "access_token = \'SYNTHETIC-ONLY-NESTED-STRING\'"\n',
        'payload = \'{"password": "SYNTHETIC-ONLY-JSON-STRING"}\'\n',
        'message = \'# password = "<value omitted>"\'\n',
    ],
    ids=("unrelated-string", "nested-string", "json-string", "comment-text-string"),
)
def test_scanners_reject_concrete_credentials_in_unrelated_python_strings(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic unrelated string credential")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


@pytest.mark.parametrize(
    "source",
    [
        "config.api_key = load_secret()\n",
        'vault["api_key"] = os.environ["API_KEY"]\n',
        'vault["credentials"]["passphrase"] = getpass.getpass()\n',
        'message = "api_key = <value omitted>"\n',
    ],
    ids=("attribute-loader", "subscript-environment", "nested-prompt", "value-free-string"),
)
def test_scanners_keep_narrow_value_free_attribute_subscript_and_string_contexts(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic value-free credential context")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 0
    assert release_candidate_check._python_credential_finding(source) is False


@pytest.mark.parametrize(
    "source",
    [
        '# api_key = "SYNTHETIC-ONLY-COMMENT-CREDENTIAL"\n',
        'value = 1  # access_token = "SYNTHETIC-ONLY-INLINE-CREDENTIAL"\n',
        '# {"credentials": {"password": "SYNTHETIC-ONLY-NESTED-COMMENT"}}\n',
        '# api\u200b_\u2060key\u00a0=\u00a0"SYNTHETIC-ONLY-UNICODE-COMMENT"\n',
    ],
    ids=("ordinary", "inline", "nested", "unicode-default-ignorable"),
)
def test_scanners_reject_concrete_credentials_in_python_comments(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic comment credential")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


@pytest.mark.parametrize(
    "source",
    [
        "# api_key is loaded from the protected local vault; value omitted\n",
        "value = 1  # passphrase is requested locally; no value is committed\n",
        '# {"credentials": {"password": "<value omitted>"}}\n',
        "# api\u200b_\u2060key\u00a0is a name only; no value is stored\n",
    ],
    ids=("ordinary-policy", "inline-policy", "nested-policy", "unicode-policy"),
)
def test_scanners_allow_only_value_free_tokenized_policy_comments(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic value-free comment policy")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 0
    assert release_candidate_check._python_credential_finding(source) is False


def _malformed_comment_sources() -> list[str]:
    encoded_value = base64.b64encode(
        b"SYNTHETIC-ONLY-MALFORMED-ENCODED-COMMENT"
    ).decode("ascii")
    return [
        "def broken(:\n# api_key = 'SYNTHETIC-ONLY-MALFORMED-BEFORE'\n",
        "# api_key = 'SYNTHETIC-ONLY-MALFORMED-AFTER'\ndef broken(:\n",
        "value = 1  # access_token = 'SYNTHETIC-ONLY-MALFORMED-INLINE'\n"
        "def broken(:\n",
        "# {\"credentials\": {\"password\": \"SYNTHETIC-ONLY-MALFORMED-NESTED\"}}\n"
        "def broken(:\n",
        "def broken(:\n# api\u200b_\u2060key\u00a0=\u00a0"
        "'SYNTHETIC-ONLY-MALFORMED-UNICODE'\n",
        f'def broken(:\n# api_key = "{encoded_value}"\n',
    ]


@pytest.mark.parametrize(
    "source",
    _malformed_comment_sources(),
    ids=("ordinary-before", "ordinary-after", "inline", "nested-looking", "unicode-default-ignorable", "encoded"),
)
def test_scanners_reject_credentials_in_malformed_python_comments(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic malformed comment credential")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


@pytest.mark.parametrize(
    "source",
    [
        "def broken(:\n# api_key is loaded locally; value omitted\n",
        "value = (\n# api_key is loaded locally; value omitted\n",
        "# {\"credentials\": {\"password\": \"<value omitted>\"}}\nvalue = (\n",
    ],
    ids=("syntax-error-value-free", "tokenization-error-value-free", "tokenization-error-placeholder"),
)
def test_scanners_fail_closed_on_malformed_value_free_python(
    tmp_path: Path, source: str
) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic malformed value-free Python")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


@pytest.mark.parametrize(
    "source",
    [
        'api_key = "SYNTHETIC-ONLY-MULTIPLY" * 2\n',
        "api_key = f\"{'SYNTHETIC-ONLY-FSTRING'}\"\n",
        'api_key = "{}".format("SYNTHETIC-ONLY-FORMAT")\n',
        'api_key = "credential:%s" % "SYNTHETIC-ONLY-PERCENT"\n',
        'api_key = ("%s" % ("SYNTHETIC-ONLY-NESTED" + "-VALUE")) * 1\n',
        'api_key = base64.b64decode("' + base64.b64encode(b"SYNTHETIC-ONLY-ENCODED").decode("ascii") + '").decode("utf-8")\n',
    ],
    ids=("multiply", "f-string", "format", "percent", "nested", "encoded"),
)
def test_scanners_reject_nested_and_encoded_python_credentials(tmp_path: Path, source: str) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic bounded credential expression")

    report = release_scan.scan_tracked_files(repo, ["public.py"])
    assert report.findings["credential_signature"] == 1
    assert release_candidate_check._python_credential_finding(source) is True


def test_scanners_keep_value_free_vault_names_but_reject_same_text_outside_context(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "public.py").write_text(
        "secret = load_secret()\npassphrase: str\nvalue = vault[\"secret\"]\n", encoding="utf-8"
    )
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic value-free names")
    safe = release_scan.scan_tracked_files(repo, ["public.py"])
    assert safe.findings["credential_signature"] == 0

    (repo / "public.py").write_text(
        'api_key = "SYNTHETIC-ONLY-OUTSIDE-CONTEXT"\n', encoding="utf-8"
    )
    _git(repo, "add", "public.py")
    _git(repo, "commit", "-m", "synthetic credential outside context")
    unsafe = release_scan.scan_tracked_files(repo, ["public.py"])
    assert unsafe.findings["credential_signature"] == 1


def test_scan_rejects_invalid_utf8_and_nul_bearing_blobs(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "utf16.txt").write_bytes("api_key = 'SYNTHETIC-ONLY-UTF16'".encode("utf-16"))
    _git(repo, "add", "utf16.txt")
    _git(repo, "commit", "-m", "synthetic invalid encoding")
    with pytest.raises(release_scan.ReleaseScanError, match="tracked blob"):
        release_scan.scan_tracked_files(repo, ["utf16.txt"])

    (repo / "null-content.txt").write_bytes(b"api_key = 'SYNTHETIC-ONLY-NUL'\0")
    _git(repo, "add", "null-content.txt")
    _git(repo, "commit", "-m", "synthetic nul blob")
    with pytest.raises(release_scan.ReleaseScanError, match="NUL"):
        release_scan.scan_tracked_files(repo, ["null-content.txt"])
    entry = release_candidate_check.TreeEntry("100644", "blob", "synthetic", "null-content.txt")
    assert "invalid textual blob" in release_candidate_check._blob_findings([entry], {"synthetic": b"x\0y"})


def test_scanners_scan_unicode_git_path_aliases(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    private_dir = repo / "Ｄａｔａ"
    private_dir.mkdir()
    (private_dir / "Finances.json").write_text("public-looking content\n", encoding="utf-8")
    _git(repo, "add", "Ｄａｔａ/Finances.json")
    _git(repo, "commit", "-m", "synthetic unicode private path")
    head = _git(repo, "rev-parse", "HEAD")

    report = release_scan.scan_tracked_files(repo, ["Ｄａｔａ/Finances.json"], revision=head)
    assert report.findings["private_data_path"] == 1
    candidate_entry = release_candidate_check.TreeEntry("100644", "blob", "synthetic", "Ｄａｔａ/Finances.json")
    assert any("private-runtime path" in finding for finding in release_candidate_check._path_findings([candidate_entry]))


def test_public_hash_exemption_is_exact_typed_value_only(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    digest = "0123456789abcdef" * 4
    (repo / "provenance.json").write_text(
        '{"content_sha256": "' + digest + '"}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "provenance.json")
    _git(repo, "commit", "-m", "synthetic exact hash field")
    report = release_scan.scan_tracked_files(repo, ["provenance.json"])
    assert report.findings["long_numeric_identifier"] == 0

    (repo / "provenance.json").write_text(
        '{"content_sha256": "' + digest + '", "url": "https://example.invalid/source/123456789012345"}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "provenance.json")
    _git(repo, "commit", "-m", "synthetic hash outside field")
    unsafe = release_scan.scan_tracked_files(repo, ["provenance.json"])
    assert unsafe.findings["long_numeric_identifier"] == 1
