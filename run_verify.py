"""Single verify entry point: original regressions plus the transfer ledger."""
import unittest

import transfer_examples


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    transfer_examples.verify()
    print("ALL_CHECKS_OK: original archive regressions and transfer contract pass")


if __name__ == "__main__":
    main()
