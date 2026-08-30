from unittest.mock import patch
import sys
import pytest
from rachel import proxy


def test_main_calls_freeze_support():
    with patch("multiprocessing.freeze_support") as mock_freeze, \
         patch("argparse.ArgumentParser.parse_args") as mock_args, \
         patch("uvicorn.run") as mock_run:
        mock_args.return_value.host = "127.0.0.1"
        mock_args.return_value.port = 8000
        mock_args.return_value.reload = False

        proxy.main()

        assert mock_freeze.called
        assert mock_run.called


def test_main_reload_flag():
    with patch("multiprocessing.freeze_support") as mock_freeze, \
         patch("argparse.ArgumentParser.parse_args") as mock_args, \
         patch("uvicorn.run") as mock_run:
        mock_args.return_value.host = "0.0.0.0"
        mock_args.return_value.port = 9000
        mock_args.return_value.reload = True

        proxy.main()

        assert mock_freeze.called
        mock_run.assert_called_with("rachel.entrypoints.desktop:app", host="0.0.0.0", port=9000, reload=True)
