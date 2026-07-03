from jamesos.services.attachment_processor import process_pending_attachment_jobs


def main() -> None:
    print(process_pending_attachment_jobs(limit=25))


if __name__ == "__main__":
    main()
