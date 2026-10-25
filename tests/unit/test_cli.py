from typer.testing import CliRunner

from app.cli import cli


def test_cli_help_and_explicit_approval(tmp_path):
    runner = CliRunner()
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
    assert "--document-id" in runner.invoke(cli, ["reindex", "--help"]).output
    result = runner.invoke(cli, ["ingest-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "--approve" in result.output
