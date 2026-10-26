#!/usr/bin/env python3
"""Simple macOS GUI for the UnfairPlay FairPlay IPA decryptor.

Tabs map one-to-one onto the unfairplay CLI subcommands: Decrypt,
Recover, Verify, Doctor and Collect. Each tab runs the Go binary as a
subprocess and streams its output into a shared log. Collect needs
administrator rights, so it prompts for the admin password through the
native macOS dialog (osascript) instead of running unsandboxed.

For the standalone app (setup.py / py2app) the binary is bundled in the
app's Resources directory; when run from a repository checkout the
sibling `unfairplay` binary is used.
"""

from __future__ import annotations

import os
import platform
import queue
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

FROZEN = bool(getattr(sys, "frozen", False)) or "RESOURCEPATH" in os.environ
if FROZEN:
    # Inside a py2app bundle the runtime files live in Contents/Resources.
    env = os.environ.get("RESOURCEPATH")
    if env:
        ROOT = Path(env)
    else:
        ROOT = Path(sys.executable).resolve().parent.parent / "Resources"
else:
    ROOT = Path(__file__).resolve().parent
BINARY = ROOT / "unfairplay"

IS_MACOS = platform.system() == "Darwin"


class Runner:
    """Runs unfairplay subcommands and streams their output to a queue."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.returncode: int | None = None
        self.cancelled = False

    def _spawn(self, argv: list[str]) -> None:
        try:
            self.process = subprocess.Popen(
                argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as error:
            self.lines.put(f"Failed to launch: {error}")
            self.returncode = 1
            self.lines.put(None)
            return
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.lines.put(line.rstrip("\n"))
        self.returncode = self.process.wait()
        self.lines.put(None)

    def start(self, args: list[str]) -> None:
        self._spawn([str(BINARY), *args])

    def start_admin(self, args: list[str]) -> None:
        """Run a sudo-requiring command via the native admin-password dialog."""
        if not IS_MACOS:
            self.lines.put("Collect needs macOS: run it from Terminal with sudo.")
            self.returncode = 1
            self.lines.put(None)
            return
        script = "do shell script " + shlex.quote(
            shlex.join([str(BINARY), *args]) + " with administrator privileges"
        )
        self._spawn(["osascript", "-e", script])

    def cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.cancelled = True
            self.process.terminate()
            self.lines.put(None)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.runner = Runner()
        self.busy = False
        root.title("UnfairPlay")
        root.minsize(720, 520)

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.X)
        self.decrypt_frame = self.make_decrypt_tab(notebook)
        self.recover_frame = self.make_recover_tab(notebook)
        self.verify_frame = self.make_verify_tab(notebook)
        self.doctor_frame = self.make_doctor_tab(notebook)
        self.collect_frame = self.make_collect_tab(notebook)

        log_frame = ttk.LabelFrame(outer, text="Output", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 8))
        self.log = tk.Text(
            log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED, undo=False
        )
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scrollbar.set)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(
            bottom, text="Cancel", command=self.on_cancel, state=tk.DISABLED
        )
        self.cancel_button.pack(side=tk.RIGHT)

        if not BINARY.exists():
            self.append_log(
                "The 'unfairplay' binary is not built yet.\n"
                "Run `go build -o unfairplay ./cmd/unfairplay` in the repository "
                "directory, or install a release binary next to this script.\n"
            )
            self.status_var.set("Not ready: build the 'unfairplay' binary first.")

    # ---- tab builders -------------------------------------------------

    def make_decrypt_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=12)
        parent.add(frame, text="Decrypt")
        self.decrypt_input = tk.StringVar()
        self.decrypt_model = tk.StringVar()
        self.decrypt_output = tk.StringVar()
        self.decrypt_report = tk.StringVar()

        def default_outputs() -> None:
            stem = self.decrypt_input.get()
            if stem.lower().endswith(".ipa"):
                stem = stem[:-4]
                if not self.decrypt_output.get():
                    self.decrypt_output.set(stem + ".decrypted.ipa")
                if not self.decrypt_report.get():
                    self.decrypt_report.set(stem + ".decrypted.json")

        def choose_input() -> None:
            path = filedialog.askopenfilename(
                title="Encrypted IPA",
                filetypes=[("IPA", "*.ipa"), ("All files", "*")],
            )
            if path:
                self.decrypt_input.set(path)
                default_outputs()

        def choose_output() -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".ipa", title="Decrypted output"
            )
            if path:
                self.decrypt_output.set(path)

        def choose_report() -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".json", title="Decryption report"
            )
            if path:
                self.decrypt_report.set(path)

        def choose_model() -> None:
            path = filedialog.askopenfilename(
                title="Enrollment model (fairplay-enrollment.bin)"
            )
            if path:
                self.decrypt_model.set(path)

        self.row(
            frame, 0, "Encrypted IPA", self.decrypt_input, choose_input
        )
        self.row(
            frame, 1, "Enrollment model (file or directory)",
            self.decrypt_model, choose_model,
        )
        self.row(frame, 2, "Decrypted output", self.decrypt_output, choose_output)
        self.row(frame, 3, "Decryption report", self.decrypt_report, choose_report)
        self.run_button = ttk.Button(frame, text="Decrypt", command=self.on_decrypt)
        self.run_button.grid(row=4, column=1, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def make_recover_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=12)
        parent.add(frame, text="Recover")
        self.recover_capture = tk.StringVar()
        self.recover_output = tk.StringVar()

        def choose_capture() -> None:
            path = filedialog.askopenfilename(title="Capture bundle (App.capture)")
            if path:
                self.recover_capture.set(path)

        def choose_output() -> None:
            path = filedialog.askdirectory(title="New recovery output directory")
            if path:
                self.recover_output.set(path)

        self.row(frame, 0, "Capture bundle", self.recover_capture, choose_capture)
        self.row(frame, 1, "Recovery output directory (must not exist)",
                 self.recover_output, choose_output)
        self.recover_button = ttk.Button(frame, text="Recover", command=self.on_recover)
        self.recover_button.grid(row=2, column=1, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def make_verify_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=12)
        parent.add(frame, text="Verify")
        self.verify_input = tk.StringVar()
        self.verify_model = tk.StringVar()

        def choose_input() -> None:
            path = filedialog.askopenfilename(
                title="Encrypted IPA",
                filetypes=[("IPA", "*.ipa"), ("All files", "*")],
            )
            if path:
                self.verify_input.set(path)

        def choose_model() -> None:
            path = filedialog.askopenfilename(title="Enrollment model")
            if path:
                self.verify_model.set(path)

        self.row(frame, 0, "Encrypted IPA", self.verify_input, choose_input)
        self.row(frame, 1, "Enrollment model", self.verify_model, choose_model)
        self.verify_button = ttk.Button(
            frame, text="Verify (no plaintext kept)", command=self.on_verify
        )
        self.verify_button.grid(row=2, column=1, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def make_doctor_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=12)
        parent.add(frame, text="Doctor")
        self.doctor_capture = tk.StringVar()
        self.doctor_ipa = tk.StringVar()
        self.doctor_model = tk.StringVar()

        def choose(kind: str, variable: tk.StringVar, must_be_dir: bool) -> None:
            if must_be_dir:
                path = filedialog.askdirectory(title=kind)
            else:
                path = filedialog.askopenfilename(title=kind)
            if path:
                variable.set(path)

        self.row(frame, 0, "Capture directory", self.doctor_capture,
                 lambda: choose("Capture", self.doctor_capture, True))
        self.row(frame, 1, "Encrypted IPA", self.doctor_ipa,
                 lambda: choose("IPA", self.doctor_ipa, False))
        self.row(frame, 2, "Enrollment model", self.doctor_model,
                 lambda: choose("Model", self.doctor_model, False))
        ttk.Label(
            frame, text="Leave fields empty to diagnose only what is filled in.",
            foreground="gray",
        ).grid(row=3, column=1, sticky="w")
        self.doctor_button = ttk.Button(frame, text="Doctor", command=self.on_doctor)
        self.doctor_button.grid(row=4, column=1, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def make_collect_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=12)
        parent.add(frame, text="Collect")
        self.collect_app = tk.StringVar()
        self.collect_ipa = tk.StringVar()
        self.collect_output = tk.StringVar()

        def choose_app() -> None:
            path = filedialog.askopenfilename(title="Installed App Store .app")
            if path:
                self.collect_app.set(path)

        def choose_ipa() -> None:
            path = filedialog.askopenfilename(
                title="Matching personalized IPA",
                filetypes=[("IPA", "*.ipa"), ("All files", "*")],
            )
            if path:
                self.collect_ipa.set(path)

        def choose_output() -> None:
            path = filedialog.asksaveasfilename(title="New capture bundle")
            if path:
                self.collect_output.set(path)

        self.row(frame, 0, "Installed .app", self.collect_app, choose_app)
        self.row(frame, 1, "Matching encrypted IPA", self.collect_ipa, choose_ipa)
        self.row(frame, 2, "New capture output", self.collect_output, choose_output)
        ttk.Label(
            frame,
            text="Runs with administrator privileges (macOS password prompt).",
            foreground="gray",
        ).grid(row=3, column=1, sticky="w")
        self.collect_button = ttk.Button(frame, text="Collect…", command=self.on_collect)
        self.collect_button.grid(row=4, column=1, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def row(
        self, parent: ttk.Frame, index: int, label: str,
        variable: tk.StringVar, choose,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", pady=(0, 4))
        row = ttk.Frame(parent)
        row.grid(row=index, column=1, sticky="ew", pady=(0, 4))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Choose…", command=choose).pack(side=tk.LEFT, padx=(6, 0))

    # ---- log and run loop ---------------------------------------------

    def append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text if text.endswith("\n") else text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def require_binary(self) -> bool:
        if not BINARY.exists():
            messagebox.showerror(
                "UnfairPlay",
                "The 'unfairplay' binary is missing. Build it with "
                "`go build -o unfairplay ./cmd/unfairplay` or install a "
                "release binary next to this script.",
            )
            return False
        return True

    def begin(self, title: str, runner_start) -> None:
        self.busy = True
        self.status_var.set(f"Running {title}…")
        self.cancel_button.configure(state=tk.NORMAL)
        for button in self.all_run_buttons():
            button.configure(state=tk.DISABLED)
        runner_start()
        self.root.after(200, self.poll)

    def all_run_buttons(self) -> list[ttk.Button]:
        return [self.run_button, self.recover_button, self.verify_button,
                self.doctor_button, self.collect_button]

    def finish(self, code: int | None) -> None:
        self.busy = False
        self.cancel_button.configure(state=tk.DISABLED)
        for button in self.all_run_buttons():
            button.configure(state=tk.NORMAL)
        if code == 0:
            self.status_var.set("Done.")
        elif code is None or self.runner.cancelled:
            self.status_var.set("Cancelled.")
            self.append_log("Cancelled.")
        else:
            self.status_var.set(f"Failed (exit {code}). See output above.")

    def poll(self) -> None:
        finished = False
        while True:
            try:
                item = self.runner.lines.get_nowait()
            except queue.Empty:
                break
            if item is None:
                finished = True
                break
            self.append_log(item)
        if finished:
            self.finish(self.runner.returncode)
        elif self.busy:
            self.root.after(200, self.poll)

    # ---- command handlers ----------------------------------------------

    def on_decrypt(self) -> None:
        if not self.require_binary():
            return
        ipa = self.decrypt_input.get()
        model = self.decrypt_model.get()
        if not ipa or not Path(ipa).is_file():
            messagebox.showerror("UnfairPlay", "Choose the encrypted IPA.")
            return
        if not model:
            messagebox.showerror("UnfairPlay", "Choose the enrollment model.")
            return
        output = self.decrypt_output.get()
        report = self.decrypt_report.get()
        if output and Path(output).exists():
            messagebox.showerror(
                "UnfairPlay", "Output already exists; pick another path."
            )
            return
        args = ["decrypt", "--input", ipa, "--model", model]
        if output:
            args += ["--output", output]
        if report:
            args += ["--report", report]
        self.append_log(f"$ unfairplay {shlex.join(args)}")
        self.begin("decrypt", lambda: self.runner.start(args))

    def on_recover(self) -> None:
        if not self.require_binary():
            return
        capture = self.recover_capture.get()
        output = self.recover_output.get()
        if not capture or not Path(capture).exists():
            messagebox.showerror("UnfairPlay", "Choose the capture bundle.")
            return
        if not output:
            messagebox.showerror("UnfairPlay", "Choose the recovery output directory.")
            return
        if Path(output).exists():
            messagebox.showerror(
                "UnfairPlay", "Recovery output directory already exists."
            )
            return
        args = ["recover", "--capture", capture, "--output", output]
        self.append_log(f"$ unfairplay {shlex.join(args)}")
        self.begin("recover", lambda: self.runner.start(args))

    def on_verify(self) -> None:
        if not self.require_binary():
            return
        ipa = self.verify_input.get()
        model = self.verify_model.get()
        if not ipa or not Path(ipa).is_file():
            messagebox.showerror("UnfairPlay", "Choose the encrypted IPA.")
            return
        if not model:
            messagebox.showerror("UnfairPlay", "Choose the enrollment model.")
            return
        args = ["verify", "--input", ipa, "--model", model]
        self.append_log(f"$ unfairplay {shlex.join(args)}")
        self.begin("verify", lambda: self.runner.start(args))

    def on_doctor(self) -> None:
        if not self.require_binary():
            return
        args = ["doctor"]
        for flag, value in (
            ("--capture", self.doctor_capture.get()),
            ("--ipa", self.doctor_ipa.get()),
            ("--model", self.doctor_model.get()),
        ):
            if value:
                args += [flag, value]
        if len(args) == 1:
            messagebox.showerror(
                "UnfairPlay", "Fill at least one field to diagnose."
            )
            return
        self.append_log(f"$ unfairplay {shlex.join(args)}")
        self.begin("doctor", lambda: self.runner.start(args))

    def on_collect(self) -> None:
        if not self.require_binary():
            return
        app = self.collect_app.get()
        ipa = self.collect_ipa.get()
        output = self.collect_output.get()
        if not app or not Path(app).exists():
            messagebox.showerror("UnfairPlay", "Choose the installed .app.")
            return
        if not ipa or not Path(ipa).is_file():
            messagebox.showerror("UnfairPlay", "Choose the matching IPA.")
            return
        if not output:
            messagebox.showerror("UnfairPlay", "Choose the capture output.")
            return
        if Path(output).exists():
            messagebox.showerror("UnfairPlay", "Capture output already exists.")
            return
        args = ["collect", "--app", app, "--ipa", ipa, "--output", output]
        self.append_log(f"$ sudo unfairplay {shlex.join(args)}")
        self.begin("collect", lambda: self.runner.start_admin(args))

    def on_cancel(self) -> None:
        self.runner.cancel()
        self.status_var.set("Cancelling…")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()