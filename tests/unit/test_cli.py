import re

from typer.testing import CliRunner

from app.cli import cli


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def test_cli_help_and_explicit_approval(tmp_path):
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})
    assert runner.invoke(cli, ["--help"]).exit_code == 0
    for command in [
        "doctor",
        "ingest-dir",
        "import-manifest",
        "worker",
        "jobs",
        "sources",
        "reindex",
        "query",
        "eval",
        "eval-passages",
        "create-collection",
        "reembed",
    ]:
        result = runner.invoke(cli, [command, "--help"])
        assert result.exit_code == 0, result.output
    reindex_output = strip_ansi(runner.invoke(cli, ["reindex", "--help"]).output)
    assert "--document-id" in reindex_output
    result = runner.invoke(cli, ["ingest-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "--approve" in strip_ansi(result.output)
