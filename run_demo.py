"""Single demo entry point: real conservation transfer plus the archive demo."""
import demo
import transfer_examples


def main():
    print("== conservation transfer (holed source, partial cover, "
          "in-hole and contact-only targets) ==")
    transfer_examples.demo()
    print()
    print("== original exact region archive ==")
    demo.main()


if __name__ == "__main__":
    main()
