from pathlib import Path
import pytest
import site

# Ensure pandas from the local virtual environment is importable
root_dir = Path(__file__).resolve().parent.parent
venv_site = root_dir / '.venv' / 'lib' / 'python3.10' / 'site-packages'
if venv_site.exists():
    site.addsitedir(str(venv_site))

pandas = pytest.importorskip('pandas')

from src.parser import parse_chat_json


def test_parse_chat_json_example():
    json_file = (
        Path(__file__).resolve().parent / 'fixtures' / 'parser_chat_example.json'
    )
    df = parse_chat_json(str(json_file))
    expected_columns = ['tabId', 'chatTitle', 'type', 'messageType', 'id', 'requestId', 'text', 'rawText', 'modelType', 'hasCodeBlock', 'timestamp']
    assert list(df.columns) == expected_columns
    assert len(df) == 8
