"""Entry point for VHDeployX."""

import sys


def main():
    from vhdeployx.app import VHDeployXApp

    app = VHDeployXApp()
    app.mainloop()


if __name__ == "__main__":
    main()
