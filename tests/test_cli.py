"""CLI 模組煙霧測試。"""
import argparse

from src.cli.parser import build_parser
from src.cli.run import dispatch, _normalize_signals_args


def test_build_parser():
    p = build_parser()
    assert isinstance(p, argparse.ArgumentParser)


def test_dispatch_serve_parses():
    p = build_parser()
    args = p.parse_args(["serve", "--port", "9999"])
    assert args.command == "serve"
    assert args.port == 9999


def test_normalize_signals_args():
    args = argparse.Namespace(action="history", codes=["600519"], code=None)
    _normalize_signals_args(args)
    assert args.code == "600519"
