# coding=utf-8
"""入口：python -m voice_reader"""
import sys


def main():
    from .ui import main as ui_main
    ui_main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
