import sys
import asyncio
from PySide6.QtWidgets import QApplication
import qasync

from main_window import MainWindow

# Main data structures for holding the data stream configs


if __name__ == "__main__":
    app = QApplication(sys.argv)

    if sys.platform == "win32" and sys.version_info >= (3, 8):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception as e:
            print(f"Could not set WindowsSelectorEventLoopPolicy: {e}")

    # Create a QAsync event loop and set it as the current asyncio loop
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    main_window = MainWindow(loop=event_loop)
    main_window.show()

    try:
        with event_loop:  # Context manager starts and closes the loop
            event_loop.run_forever()
    except KeyboardInterrupt:
        print("User interrupted, shutting down.")
    finally:
        if not event_loop.is_closed():
            print("Closing QAsync event loop...")
            # Gather all tasks and cancel them
            tasks = asyncio.all_tasks(loop=event_loop)
            for task in tasks:
                task.cancel()
            # Give tasks a chance to cancel
            event_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            event_loop.close()
        print("Exiting.")

    sys.exit(0)