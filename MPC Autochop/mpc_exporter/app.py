from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .exporter import ExportOptions, ExportResult, export_folder


class MPCFolderChopper:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MPC Folder Chopper")
        self.root.minsize(560, 390)
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.beat_bar = tk.BooleanVar(value=True)
        self.onset = tk.BooleanVar(value=True)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text="Select a folder of MP3/WAV files. Both 32-pad and 64-pad MPC 3 kits "
            "will be generated for each selected chop method.",
            wraplength=510,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="Audio folder").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.input_folder).grid(
            row=2, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(frame, text="Browse...", command=self._choose_folder).grid(
            row=2, column=1, sticky="ew"
        )

        ttk.Label(frame, text="Output folder (one ZIP per track)").grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Entry(frame, textvariable=self.output_folder).grid(
            row=4, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(frame, text="Browse...", command=self._choose_output_folder).grid(
            row=4, column=1, sticky="ew"
        )

        methods = ttk.LabelFrame(frame, text="Chop methods", padding=8)
        methods.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Checkbutton(methods, text="Beat/bar aligned", variable=self.beat_bar).pack(
            side=tk.LEFT, padx=(0, 18)
        )
        ttk.Checkbutton(methods, text="Onset detection", variable=self.onset).pack(
            side=tk.LEFT
        )

        self.export_button = ttk.Button(frame, text="Analyze and export", command=self._start)
        self.export_button.grid(row=6, column=0, sticky="w", pady=14)
        self.status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status, wraplength=510).grid(
            row=7, column=0, columnspan=3, sticky="w"
        )

        self.log = tk.Text(frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(8, weight=1)
        self.root.after(100, self._drain_messages)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose a folder containing audio")
        if selected:
            self.input_folder.set(selected)
            self.output_folder.set(str(Path(selected) / "MPC_Exports"))

    def _choose_output_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose where per-track ZIP files will be saved")
        if selected:
            self.output_folder.set(selected)

    def _start(self) -> None:
        folder = Path(self.input_folder.get()).expanduser()
        output = Path(self.output_folder.get()).expanduser()
        methods = tuple(
            method
            for enabled, method in (
                (self.beat_bar.get(), "beat-bar"),
                (self.onset.get(), "onset"),
            )
            if enabled
        )
        if not folder.is_dir():
            messagebox.showerror("Invalid folder", "Choose an existing audio folder.")
            return
        if not self.output_folder.get().strip():
            messagebox.showerror("Invalid output", "Choose a folder for the per-track ZIP files.")
            return
        if not methods:
            messagebox.showerror("No chop method", "Select at least one chop method.")
            return

        self.export_button.configure(state=tk.DISABLED)
        self.status.set("Working...")
        self._append_log("Starting export.")
        options = ExportOptions(folder, output, methods)
        threading.Thread(target=self._run_export, args=(options,), daemon=True).start()

    def _run_export(self, options: ExportOptions) -> None:
        try:
            result = export_folder(options, lambda message: self.messages.put(("log", message)))
            self.messages.put(("success", result))
        except Exception as error:
            self.messages.put(("error", error))

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
                self.status.set(str(payload))
            elif kind == "success":
                result = payload
                assert isinstance(result, ExportResult)
                self.export_button.configure(state=tk.NORMAL)
                self.status.set(f"Export complete: {result.output_folder}")
                summary = (
                    f"Created {len(result.zip_paths)} per-track ZIP file(s) for "
                    f"{result.song_count} song(s), containing {result.kit_count} MPC program(s).\n"
                    f"Saved in: {result.output_folder}"
                )
                if result.errors:
                    summary += "\n\nSome files failed:\n" + "\n".join(
                        f"{name}: {reason}" for name, reason in result.errors[:5]
                    )
                    if len(result.errors) > 5:
                        summary += f"\n...and {len(result.errors) - 5} more."
                    messagebox.showwarning("Export finished with errors", summary)
                else:
                    messagebox.showinfo("Export complete", summary)
            elif kind == "error":
                error = payload
                self.export_button.configure(state=tk.NORMAL)
                self.status.set("Export failed.")
                messagebox.showerror("Export failed", str(error))
        self.root.after(100, self._drain_messages)

    def _append_log(self, message: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{message}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def main() -> None:
    root = tk.Tk()
    MPCFolderChopper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
