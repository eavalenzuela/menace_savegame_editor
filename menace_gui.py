#!/usr/bin/env python3
"""MENACE savegame editor — tkinter GUI."""

import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import uuid

from menace_save import (
    MenaceSave, CatalogItem,
    parse_save, serialize_save,
    increment_uuid,
)

# ── Global stats config ─────────────────────────────────────────────────────

GLOBAL_STATS_COUNT = 20

STAT_LABELS = {
    0: "Count field",
    1: "Unknown #1",
    2: "OCI Components",
    3: "Promotion Points",
    4: "Stat #4",
    5: "Stat #5",
    6: "Stat #6",
    7: "Stat #7",
    8: "Stat #8",
    9: "Stat #9",
    10: "Stat #10",
    11: "Stat #11",
    12: "Stat #12",
    13: "Stat #13",
    14: "Intelligence",
    15: "Stat #15",
    16: "Authority",
    17: "Stat #17",
    18: "Stat #18",
    19: "Stat #19",
}


def _find_stats_offset(data: bytes) -> int:
    """Find the byte offset where global stats begin.

    Stats follow the second occurrence of 'global_difficulty.normal'
    in the pre-catalog header. The offset varies with header string lengths.
    """
    needle = b'global_difficulty.normal'
    first = data.find(needle)
    if first < 0:
        raise ValueError("Could not find 'global_difficulty.normal' in header")
    second = data.find(needle, first + len(needle))
    if second < 0:
        raise ValueError("Could not find second 'global_difficulty.normal' in header")
    return second + len(needle)


def read_global_stats(pre_catalog: bytes) -> list[int]:
    """Read global stats u32 values from pre_catalog blob."""
    offset = _find_stats_offset(pre_catalog)
    stats = []
    for i in range(GLOBAL_STATS_COUNT):
        off = offset + i * 4
        if off + 4 <= len(pre_catalog):
            val = struct.unpack_from('<I', pre_catalog, off)[0]
            stats.append(val)
        else:
            stats.append(0)
    return stats


def write_global_stats(pre_catalog: bytearray, stats: list[int]) -> bytearray:
    """Write global stats back into pre_catalog blob."""
    buf = bytearray(pre_catalog)
    offset = _find_stats_offset(bytes(buf))
    for i, val in enumerate(stats):
        off = offset + i * 4
        if off + 4 <= len(buf):
            struct.pack_into('<I', buf, off, val)
    return buf


def item_category(item_type: str) -> str:
    """Extract category prefix from an item type string."""
    dot = item_type.find('.')
    if dot > 0:
        return item_type[:dot]
    return item_type


# ── Main application ────────────────────────────────────────────────────────

class MenaceEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MENACE Savegame Editor")
        self.geometry("950x620")
        self.minsize(750, 450)

        self.save: MenaceSave | None = None
        self.filepath: str | None = None
        self.stat_vars: list[tk.StringVar] = []

        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────────

    def _build_ui(self):
        # File bar
        file_frame = ttk.Frame(self)
        file_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        ttk.Label(file_frame, text="File:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, state="readonly")
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Button(file_frame, text="Open", command=self._open_file).pack(side=tk.LEFT, padx=2)
        self.save_btn = ttk.Button(file_frame, text="Save", command=self._save_file, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=2)
        self.saveas_btn = ttk.Button(file_frame, text="Save As", command=self._save_file_as, state=tk.DISABLED)
        self.saveas_btn.pack(side=tk.LEFT, padx=2)

        # Main paned window
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # Left: tabs
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_inventory_tab()
        self._build_stats_tab()

        # Right: details
        self.detail_frame = ttk.LabelFrame(paned, text="Details")
        paned.add(self.detail_frame, weight=1)

        self.detail_placeholder = ttk.Label(self.detail_frame, text="Open a save file and\nselect an item to view details.",
                                            justify=tk.CENTER, foreground="gray")
        self.detail_placeholder.pack(expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="No file loaded.")
        status = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(fill=tk.X, padx=6, pady=(0, 6))

    def _build_inventory_tab(self):
        inv_frame = ttk.Frame(self.notebook)
        self.notebook.add(inv_frame, text="Inventory")

        # Search + show all
        top = ttk.Frame(inv_frame)
        top.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(top, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_tree())
        search_entry = ttk.Entry(top, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))

        self.show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Show all", variable=self.show_all_var,
                        command=self._refresh_tree).pack(side=tk.LEFT)

        # Treeview
        tree_frame = ttk.Frame(inv_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.tree = ttk.Treeview(tree_frame, columns=("count",), selectmode="browse")
        self.tree.heading("#0", text="Item", anchor=tk.W)
        self.tree.heading("count", text="Owned", anchor=tk.W)
        self.tree.column("count", width=60, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _build_stats_tab(self):
        stats_outer = ttk.Frame(self.notebook)
        self.notebook.add(stats_outer, text="Stats")

        canvas = tk.Canvas(stats_outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(stats_outer, orient=tk.VERTICAL, command=canvas.yview)
        self.stats_frame = ttk.Frame(canvas)

        self.stats_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.stats_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── File operations ─────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open MENACE Save",
            filetypes=[("Save files", "*.save"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.save = parse_save(path)
            self.filepath = path
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse save:\n{e}")
            return

        self.file_var.set(path)
        self.save_btn.configure(state=tk.NORMAL)
        self.saveas_btn.configure(state=tk.NORMAL)

        owned = sum(1 for i in self.save.catalog if i.count > 0)
        total = sum(i.count for i in self.save.catalog)
        self.status_var.set(f"Loaded {Path(path).name}  —  {len(self.save.catalog)} item types, "
                           f"{owned} owned, {total} instances")

        self._refresh_tree()
        self._refresh_stats()
        self._clear_details()

    def _save_file(self):
        if not self.save or not self.filepath:
            return
        self._apply_stats()
        self._do_save(self.filepath)

    def _save_file_as(self):
        if not self.save:
            return
        path = filedialog.asksaveasfilename(
            title="Save As",
            defaultextension=".save",
            filetypes=[("Save files", "*.save"), ("All files", "*.*")],
        )
        if not path:
            return
        self._apply_stats()
        self._do_save(path)

    def _do_save(self, path: str):
        # Backup if overwriting the original
        if path == self.filepath:
            backup = Path(path).with_suffix('.save.bak')
            with open(path, 'rb') as f:
                backup.write_bytes(f.read())

        try:
            data = serialize_save(self.save)
            with open(path, 'wb') as f:
                f.write(data)
            self.status_var.set(f"Saved to {Path(path).name} ({len(data)} bytes)")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    # ── Inventory tree ──────────────────────────────────────────────────

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.save:
            return

        search = self.search_var.get().lower()
        show_all = self.show_all_var.get()

        # Group items by category
        categories: dict[str, list[tuple[int, CatalogItem]]] = {}
        for idx, item in enumerate(self.save.catalog):
            if not show_all and item.count == 0:
                continue
            if search and search not in item.item_type.lower():
                continue
            cat = item_category(item.item_type)
            categories.setdefault(cat, []).append((idx, item))

        for cat in sorted(categories):
            items = categories[cat]
            owned_in_cat = sum(i.count for _, i in items)
            cat_id = self.tree.insert("", tk.END, text=cat,
                                      values=(f"{owned_in_cat}",),
                                      open=bool(search))
            for idx, item in items:
                # Strip category prefix for cleaner display
                short = item.item_type[len(cat)+1:] if item.item_type.startswith(cat + ".") else item.item_type
                count_str = str(item.count) if item.count > 0 else "-"
                self.tree.insert(cat_id, tk.END, text=short,
                                 values=(count_str,),
                                 tags=(str(idx),))

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        tags = self.tree.item(sel[0], "tags")
        if not tags:
            # Category row selected
            self._clear_details()
            return
        idx = int(tags[0])
        self._show_item_details(idx)

    # ── Details panel ───────────────────────────────────────────────────

    def _clear_details(self):
        for w in self.detail_frame.winfo_children():
            w.destroy()
        self.detail_placeholder = ttk.Label(self.detail_frame,
                                            text="Select an item to view details.",
                                            justify=tk.CENTER, foreground="gray")
        self.detail_placeholder.pack(expand=True)

    def _show_item_details(self, idx: int):
        for w in self.detail_frame.winfo_children():
            w.destroy()

        item = self.save.catalog[idx]
        pad = dict(padx=8, pady=2)

        ttk.Label(self.detail_frame, text=item.item_type,
                  font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Label(self.detail_frame, text=f"Owned: {item.count}").pack(anchor=tk.W, **pad)

        if item.uuids:
            ttk.Separator(self.detail_frame).pack(fill=tk.X, padx=8, pady=6)
            ttk.Label(self.detail_frame, text="UUIDs:").pack(anchor=tk.W, **pad)

            uuid_frame = ttk.Frame(self.detail_frame)
            uuid_frame.pack(fill=tk.BOTH, expand=True, padx=8)

            uuid_list = tk.Listbox(uuid_frame, height=min(len(item.uuids), 8),
                                   font=("TkFixedFont", 9))
            uuid_sb = ttk.Scrollbar(uuid_frame, orient=tk.VERTICAL, command=uuid_list.yview)
            uuid_list.configure(yscrollcommand=uuid_sb.set)
            for u in item.uuids:
                uuid_list.insert(tk.END, u)
            uuid_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            uuid_sb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Separator(self.detail_frame).pack(fill=tk.X, padx=8, pady=6)

        # Action buttons
        action_frame = ttk.Frame(self.detail_frame)
        action_frame.pack(anchor=tk.W, padx=8, pady=4)

        count_var = tk.IntVar(value=max(item.count, 1))
        ttk.Label(action_frame, text="Count:").grid(row=0, column=0, padx=(0, 4))
        count_spin = ttk.Spinbox(action_frame, from_=0, to=999, width=5,
                                 textvariable=count_var)
        count_spin.grid(row=0, column=1, padx=(0, 8))

        ttk.Button(action_frame, text="Set Count",
                   command=lambda: self._set_item_count(idx, count_var.get())
                   ).grid(row=0, column=2, padx=2)

    def _set_item_count(self, idx: int, target: int):
        item = self.save.catalog[idx]
        current = item.count
        if target == current:
            return
        if target < 0:
            target = 0

        if target > current:
            # Add instances
            to_add = target - current
            if item.uuids:
                last = item.uuids[-1]
            else:
                last = str(uuid.uuid4())
                item.uuids.append(last)
                to_add -= 1
            for _ in range(to_add):
                last = increment_uuid(last)
                item.uuids.append(last)
            self.status_var.set(f"Set {item.item_type} to x{item.count}  (+{target - current})")
        else:
            # Remove from the end
            removed = current - target
            del item.uuids[target:]
            self.status_var.set(f"Set {item.item_type} to x{item.count}  (-{removed})")

        self._refresh_tree()
        self._show_item_details(idx)

    # ── Stats tab ───────────────────────────────────────────────────────

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        self.stat_vars.clear()

        if not self.save:
            return

        stats = read_global_stats(self.save.pre_catalog)
        base_offset = _find_stats_offset(self.save.pre_catalog)

        ttk.Label(self.stats_frame, text="Global Stats",
                  font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, columnspan=2,
                                                           sticky=tk.W, padx=8, pady=(8, 4))

        for i, val in enumerate(stats):
            label = STAT_LABELS.get(i, f"Stat #{i}")
            offset = base_offset + i * 4
            display = f"{label}  (0x{offset:04X})"

            ttk.Label(self.stats_frame, text=display).grid(row=i+1, column=0,
                                                           sticky=tk.W, padx=(8, 4), pady=2)
            var = tk.StringVar(value=str(val))
            self.stat_vars.append(var)
            entry = ttk.Entry(self.stats_frame, textvariable=var, width=12)
            entry.grid(row=i+1, column=1, sticky=tk.W, padx=(0, 8), pady=2)

    def _apply_stats(self):
        """Write stat entry values back into pre_catalog."""
        if not self.save or not self.stat_vars:
            return
        stats = []
        for i, var in enumerate(self.stat_vars):
            try:
                stats.append(int(var.get()))
            except ValueError:
                label = STAT_LABELS.get(i, f"Stat #{i}")
                messagebox.showerror("Invalid value", f"{label} must be an integer.")
                return
        self.save.pre_catalog = bytes(write_global_stats(bytearray(self.save.pre_catalog), stats))


def main():
    app = MenaceEditor()
    app.mainloop()


if __name__ == '__main__':
    main()
