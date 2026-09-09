import json
import os
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL = "https://uppsc.up.nic.in/FooterPages/Latest-News"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = Path("uppsc_sent_updates.json")

# The matching is case-insensitive.
KEYWORD = "list of provisionally selected candidates"

HEADERS = {
    "User-Agent": "Mozilla/5.0 UPPSC-Monitor/1.0"
}


def fetch_matching_updates():
    """
    Returns:
        list: Matching announcements
        None: Request or parsing failure
    """

    try:
        response = requests.get(
            URL,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        updates = []
        seen_ids = set()

        for link in soup.find_all("a", href=True):
            text = " ".join(
                link.get_text(" ", strip=True).split()
            )

            if not text:
                continue

            if KEYWORD not in text.lower():
                continue

            link_url = urljoin(
                response.url,
                link["href"],
            )

            # Text + URL together identify the announcement.
            update_id = f"{text}|{link_url}"

            if update_id in seen_ids:
                continue

            seen_ids.add(update_id)

            updates.append(
                {
                    "id": update_id,
                    "text": text,
                    "url": link_url,
                }
            )

        return updates

    except requests.RequestException as error:
        print(f"UPPSC request failed: {error}")
        return None

    except Exception as error:
        print(f"Unexpected parsing error: {error}")
        return None


def read_saved_state():
    """
    Returns:
        set of previously sent update IDs
    """

    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, list):
            print("State file is not a list. Starting with empty state.")
            return set()

        return set(data)

    except (
        json.JSONDecodeError,
        OSError,
    ) as error:
        print(f"Could not read state file: {error}")
        return set()


def save_state(update_ids):
    STATE_FILE.write_text(
        json.dumps(
            sorted(update_ids),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def send_telegram(message):
    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API returned an error: {result}"
        )


def main():
    current_updates = fetch_matching_updates()

    # Failed request: do not alert and do not overwrite state.
    if current_updates is None:
        print("Request failed. Previous state preserved.")
        return

    previous_ids = read_saved_state()

    current_ids = {
        update["id"]
        for update in current_updates
    }

    # First run:
    # save all currently visible matching announcements silently.
    if not STATE_FILE.exists():
        save_state(current_ids)

        print(
            f"Initial baseline saved: "
            f"{len(current_ids)} matching update(s). "
            "No Telegram message sent."
        )

        return

    new_updates = [
        update
        for update in current_updates
        if update["id"] not in previous_ids
    ]

    if not new_updates:
        print("No new matching UPPSC updates.")
        return

    # Send each new announcement.
    for update in new_updates:
        message = (
            "🟢 New UPPSC Update\n\n"
            f"{update['text']}\n\n"
            f"Official link:\n{update['url']}"
        )

        send_telegram(message)

        print(
            f"Telegram notification sent: "
            f"{update['text']}"
        )

    # Save state only after all Telegram messages succeed.
    save_state(current_ids)

    print(
        f"Sent {len(new_updates)} new update(s). "
        "State saved successfully."
    )


if __name__ == "__main__":
    main()
