"""Entry point for: python -m daily_beltway"""
import sys
import os

# Ensure project root is on the path when run as `python -m daily_beltway`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import cli

if __name__ == "__main__":
    cli()
