# -*- coding: utf-8 -*-
__author__ = "Yahya Morcy"

import os
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import System
from System.Windows import Thickness, Visibility, HorizontalAlignment, VerticalAlignment
from System.Windows.Controls import StackPanel, CheckBox, Button
from System.Windows.Forms import OpenFileDialog, SaveFileDialog, DialogResult

from pyrevit import DB, forms

import emperor_ui
import linkmgr_ui as ui
import linkmgr_ops as ops
from linkmgr_common import doc, DOT, CHEV_CLOSED, CHEV_OPEN, eid, doevents
from linkmgr_widgets import tb, table_row as make_row, RED, RED_DARK, MUTED, WHITE
from linkmgr_data import (collect_links, sort_rows, row_matches, all_sites, is_problem,
                          room_bounding_param, NO_SITE, ALL_SITES)
from linkmgr_copy import (open_target_models, build_preview, copy_items_to_target, COPY_STATE,
                          reset_copy_state)

# Table layouts: (header, pixel width). LINK_SORT: sort key per link column (None = not sortable).
LINK_COLS = [("", 30), ("", 36), ("Link name", 300), ("Status", 90), ("Reference", 95),
             ("Room bounding", 112), ("Path type", 90), ("Link workset", 150), ("Shared site", 150),
             ("Pinned", 105), ("Instances", 80), ("Path", 420)]
LINK_SORT = [None, None, "name", "status", "attach", "room_bounding", "path_type", "workset",
             "shared_site", "pinned", "instances", "path"]
INST_COLS = [("", 40), ("Instance", 300), ("Pinned", 90), ("Shared position", 200),
             ("Shared site", 150), ("X, Y, Z (m)", 250), ("Rotation", 80),
             ("Instance workset", 150), ("Level", 210), ("", 80)]
PREVIEW_COLS = [("Link", 330), ("Instances", 80), ("Shared sites used", 260),
                ("Site check", 230), ("Already in target", 200)]


def plural(n, word):
    return u"{} {}{}".format(n, word, u"" if n == 1 else u"s")


# ----------------------------------------------------------------------------
# Link files dialog
# ----------------------------------------------------------------------------
class LinkFilesWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, ui.link_xaml(), literal_string=True)
        emperor_ui.enable_mouse_glow(self)
        self.files = []
        self.result = None
        self.BtnAdd.Click += self.on_add
        self.BtnRemove.Click += self.on_remove
        self.BtnClear.Click += self.on_clear
        self.BtnGo.Click += self.on_go
        self.BtnCancel.Click += self.on_cancel
        self.refresh_list()

    def refresh_list(self):
        self.FileList.Items.Clear()
        for f in self.files:
            self.FileList.Items.Add(f)
        n = len(self.files)
        self.BtnGo.IsEnabled = n > 0
        self.BtnGo.Content = "Link {} file{}".format(n, "" if n == 1 else "s") if n else "Link files"
        self.StatusText.Text = "{} file{} selected".format(n, "" if n == 1 else "s")

    def on_add(self, sender, args):
        dlg = OpenFileDialog()
        dlg.Multiselect = True
        dlg.Filter = "Revit models (*.rvt)|*.rvt"
        dlg.Title = "Select the Revit models to link"
        if dlg.ShowDialog() == DialogResult.OK:
            for f in dlg.FileNames:
                if f not in self.files:
                    self.files.append(f)
            self.files.sort(key=lambda p: os.path.basename(p).lower())
            self.refresh_list()

    def on_remove(self, sender, args):
        for item in list(self.FileList.SelectedItems):
            if item in self.files:
                self.files.remove(item)
        self.refresh_list()

    def on_clear(self, sender, args):
        self.files = []
        self.refresh_list()

    def on_cancel(self, sender, args):
        self.result = None
        self.Close()

    def on_go(self, sender, args):
        placement = "Shared" if self.RbShared.IsChecked else "Origin"
        ws_opt = ["OpenLastViewed", "OpenAllWorksets", "CloseAllWorksets"][
            max(0, self.CbWorksets.SelectedIndex)]
        self.result = {
            "files": list(self.files),
            "relative": bool(self.RbRelative.IsChecked),
            "overlay": bool(self.RbOverlay.IsChecked),
            "placement": placement,
            "worksets": ws_opt,
            "pin": bool(self.ChkPin.IsChecked),
            "room_bounding": bool(self.ChkRoomBounding.IsChecked),
        }
        self.Close()


# ----------------------------------------------------------------------------
# Pick the target model(s) among the models open in this Revit session
# ----------------------------------------------------------------------------
class PickModelWindow(forms.WPFWindow):
    def __init__(self, docs):
        forms.WPFWindow.__init__(self, ui.pick_xaml(), literal_string=True)
        emperor_ui.enable_mouse_glow(self)
        self.docs = docs
        self.result = []
        for d in docs:
            self.ModelList.Items.Add(u"{}      {}".format(d.Title, d.PathName or "(not saved)"))
        self.ModelList.SelectedIndex = 0
        self.BtnGo.Click += self.on_go
        self.BtnCancel.Click += self.on_cancel

    def on_go(self, sender, args):
        idx = sorted(self.ModelList.Items.IndexOf(it) for it in self.ModelList.SelectedItems)
        self.result = [self.docs[i] for i in idx if 0 <= i < len(self.docs)]
        self.Close()

    def on_cancel(self, sender, args):
        self.result = []
        self.Close()


# ----------------------------------------------------------------------------
# Copy options + preview
# ----------------------------------------------------------------------------
class CopyOptionsWindow(forms.WPFWindow):
    def __init__(self, targets, items, preview):
        forms.WPFWindow.__init__(self, ui.copy_xaml(), literal_string=True)
        emperor_ui.enable_mouse_glow(self)
        self.accepted = False
        self.unshared_exact = True
        self.policy = "skip"
        self.TargetText.Text = u"Target{}: {}".format(
            u"" if len(targets) == 1 else u"s", u",  ".join(t.Title for t in targets))
        n_inst = sum(p["count"] for p in preview)
        self.SummaryText.Text = u"{} with {} will be copied into {}.".format(
            plural(len(preview), u"link"), plural(n_inst, u"selected instance"),
            plural(len(targets), u"model"))
        self.PreviewPanel.Children.Add(make_row(PREVIEW_COLS, [c[0] for c in PREVIEW_COLS], header=True))
        for n, p in enumerate(preview):
            missing = p["site_check"].startswith(u"not found")
            self.PreviewPanel.Children.Add(make_row(
                PREVIEW_COLS,
                [p["name"], str(p["count"]), p["sites"], p["site_check"], p["present_in"]],
                alt=(n % 2 == 1), bad=missing))
        self.BtnContinue.Click += self.on_continue
        self.BtnCancel.Click += self.on_cancel

    def on_continue(self, sender, args):
        self.unshared_exact = bool(self.ChkUnsharedExact.IsChecked)
        self.policy = "add" if self.RbAdd.IsChecked else "skip"
        self.accepted = True
        self.Close()

    def on_cancel(self, sender, args):
        self.accepted = False
        self.Close()


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class LinkManagerWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, ui.main_xaml(), literal_string=True)
        emperor_ui.enable_mouse_glow(self)
        self.rows = []
        self.selected_links = set()   # link type ids
        self.selected_insts = set()   # link instance ids
        self.expanded = set()
        self.link_cbs = {}            # link id -> checkbox
        self.inst_cbs = {}            # link id -> [(instance id, checkbox)]
        self.sort_key = "name"
        self.sort_desc = False
        self._syncing = False
        self._loading = False

        self.SelectAll.Click += self.on_select_all
        self.BtnPinSel.Click += self.on_pin_selected
        self.BtnUnpinSel.Click += self.on_unpin_selected
        self.BtnPinAll.Click += self.on_pin_all
        self.BtnUnpinAll.Click += self.on_unpin_all
        self.BtnLink.Click += self.on_link_files
        self.BtnCopy.Click += self.on_copy
        self.BtnReloadAll.Click += self.on_reload_all
        self.BtnReloadSel.Click += self.on_reload_selected
        self.BtnRefresh.Click += self.on_refresh
        self.BtnUnload.Click += self.on_unload
        self.BtnRemove.Click += self.on_remove
        self.BtnOverlay.Click += self.on_overlay
        self.BtnAttachment.Click += self.on_attachment
        self.BtnRoomOn.Click += self.on_room_on
        self.BtnRoomOff.Click += self.on_room_off
        self.BtnSelectRevit.Click += self.on_select_revit
        self.BtnExport.Click += self.on_export
        self.BtnExpand.Click += self.on_expand_all
        self.BtnCollapse.Click += self.on_collapse_all
        self.BtnClose.Click += self.on_close
        self.TxtSearch.TextChanged += self.on_filter_changed
        self.CbSite.SelectionChanged += self.on_filter_changed
        self.ChkUnpinned.Click += self.on_filter_changed
        self.ChkProblems.Click += self.on_filter_changed
        self.BtnClearFilter.Click += self.on_clear_filter
        self.reload()

    # -- data / rendering ---------------------------------------------------
    def reload(self, status=None):
        self.rows = collect_links()
        link_ids = set(r["id"] for r in self.rows)
        inst_ids = set(d["id"] for r in self.rows for d in r["idata"])
        self.selected_links &= link_ids
        self.selected_insts &= inst_ids
        self.expanded &= link_ids
        self.refresh_site_combo()
        self.render()
        self.StatusText.Text = status or "Ready"

    def refresh_site_combo(self):
        self._loading = True
        try:
            current = self.CbSite.SelectedItem
            current = u"{}".format(current) if current is not None else ALL_SITES
            names = [ALL_SITES, NO_SITE] + all_sites(self.rows)
            self.CbSite.Items.Clear()
            for n in names:
                self.CbSite.Items.Add(n)
            self.CbSite.SelectedIndex = names.index(current) if current in names else 0
        finally:
            self._loading = False

    def filters_active(self):
        site = self.CbSite.SelectedItem
        return bool((self.TxtSearch.Text or u"").strip() or self.ChkUnpinned.IsChecked or
                    self.ChkProblems.IsChecked or (site is not None and u"{}".format(site) != ALL_SITES))

    def visible_rows(self):
        site = self.CbSite.SelectedItem
        site = u"{}".format(site) if site is not None else ALL_SITES
        rows = [r for r in self.rows
                if row_matches(r, self.TxtSearch.Text, site, bool(self.ChkUnpinned.IsChecked),
                               bool(self.ChkProblems.IsChecked))]
        return sort_rows(rows, self.sort_key, self.sort_desc)

    def header_cells(self):
        cells = []
        for i, col in enumerate(LINK_COLS):
            key = LINK_SORT[i]
            if key is None:
                cells.append(u"")
                continue
            arrow = u""
            if key == self.sort_key:
                arrow = u"  \u25BC" if self.sort_desc else u"  \u25B2"
            el = tb(col[0] + arrow, 12, True, WHITE)
            el.Margin = Thickness(6, 0, 6, 0)
            el.VerticalAlignment = VerticalAlignment.Center
            el.Cursor = System.Windows.Input.Cursors.Hand
            el.ToolTip = "Click to sort"
            el.Padding = Thickness(4, 2, 4, 2)
            el.MouseLeftButtonUp += self.make_sort_handler(key)
            el.MouseEnter += self._header_enter
            el.MouseLeave += self._header_leave
            cells.append(el)
        return cells

    def _header_enter(self, sender, args):
        # sortable header reacts to the mouse: light band + underline
        try:
            sender.Background = System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromArgb(0x40, 0xFF, 0xFF, 0xFF))
            sender.TextDecorations = System.Windows.TextDecorations.Underline
        except Exception:
            pass

    def _header_leave(self, sender, args):
        try:
            sender.Background = None
            sender.TextDecorations = None
        except Exception:
            pass

    def make_sort_handler(self, key):
        def handler(sender, args):
            if self.sort_key == key:
                self.sort_desc = not self.sort_desc
            else:
                self.sort_key = key
                self.sort_desc = False
            self.render()
        return handler

    def render(self):
        self.LinksPanel.Children.Clear()
        self.link_cbs = {}
        self.inst_cbs = {}
        rows = self.visible_rows()
        if not self.rows:
            self.LinksPanel.Children.Add(
                tb("This project has no Revit links yet. Use \"Link files...\" to add some.",
                   14, False, MUTED, wrap=True, margin=Thickness(4, 20, 4, 0)))
        elif not rows:
            self.LinksPanel.Children.Add(
                tb("No link matches the filters. Use \"Clear filters\" to see all links.",
                   14, False, MUTED, wrap=True, margin=Thickness(4, 20, 4, 0)))
        else:
            self.LinksPanel.Children.Add(make_row(LINK_COLS, self.header_cells(), header=True))
            for n, r in enumerate(rows):
                self.LinksPanel.Children.Add(self.build_link_row(r, n))
        total_inst = sum(len(r["idata"]) for r in self.rows)
        total_pin = sum(r["pinned_n"] for r in self.rows)
        shown = u"" if not self.filters_active() else u"{} of ".format(len(rows))
        self.SummaryText.Text = u"{}{} links  {}  {} instances  {}  {} pinned".format(
            shown, len(self.rows), DOT, total_inst, DOT, total_pin)
        self.sync_select_state()

    def make_checkbox(self, checked):
        cb = CheckBox()
        cb.Style = self.FindResource("RedCheck")
        cb.IsChecked = checked
        cb.HorizontalAlignment = HorizontalAlignment.Center
        cb.VerticalAlignment = VerticalAlignment.Center
        return cb

    def build_link_row(self, r, n):
        lid = r["id"]
        total = len(r["idata"])
        holder = StackPanel()
        bad = is_problem(r)

        chev = tb(CHEV_OPEN if lid in self.expanded else CHEV_CLOSED, 15, True, RED)
        chev.HorizontalAlignment = HorizontalAlignment.Center
        chev.VerticalAlignment = VerticalAlignment.Center
        chev.Cursor = System.Windows.Input.Cursors.Hand

        cb = self.make_checkbox(lid in self.selected_links)
        cb.Checked += self.make_link_handler(r)
        cb.Unchecked += self.make_link_handler(r)
        self.link_cbs[lid] = cb

        if total == 0:
            pin_txt = "No instances"
        elif r["pinned_n"] == total:
            pin_txt = "Pinned"
        elif r["pinned_n"] == 0:
            pin_txt = "Not pinned"
        else:
            pin_txt = "Partial {}/{}".format(r["pinned_n"], total)

        if bad:     # not loaded / not found: stand out
            status = tb(r["status"], 12.5, True, RED_DARK)
            status.Margin = Thickness(6, 0, 6, 0)
            status.VerticalAlignment = VerticalAlignment.Center
        else:
            status = r["status"]

        # Room Bounding: a check box that applies at once; "n/a" when the link type has no such parameter
        if r["room_bounding"] is None:
            room = tb("n/a", 12, False, MUTED)
            room.HorizontalAlignment = HorizontalAlignment.Center
            room.VerticalAlignment = VerticalAlignment.Center
        else:
            room = self.make_checkbox(bool(r["room_bounding"]))
            room.ToolTip = "Room Bounding of this link (applies immediately)"
            room.Checked += self.make_room_handler(r)
            room.Unchecked += self.make_room_handler(r)

        path_show = r["resolved_path"] or r["saved_path"]
        row = make_row(LINK_COLS, [chev, cb, r["name"], status, r["attach"], room, r["path_type"],
                                   r["workset"], r["shared_site"], pin_txt, str(total), path_show],
                       alt=(n % 2 == 1), bad=bad)
        row.Cursor = System.Windows.Input.Cursors.Hand
        holder.Children.Add(row)

        # instances sub-table
        sub = StackPanel()
        sub.Margin = Thickness(0, 0, 0, 6)
        sub.Visibility = Visibility.Visible if lid in self.expanded else Visibility.Collapsed
        if r["saved_path"] and r["saved_path"] != r["resolved_path"] and r["resolved_path"]:
            sub.Children.Add(self.note_row(u"Saved path:  " + r["saved_path"]))
        if total == 0:
            sub.Children.Add(self.note_row("No instances of this link are placed in the project."))
        else:
            sub.Children.Add(make_row(INST_COLS, [c[0] for c in INST_COLS], header=True, indent=64))
            self.inst_cbs[lid] = []
            for k, d in enumerate(r["idata"]):
                sub.Children.Add(make_row(INST_COLS, self.instance_cells(r, d),
                                          alt=(k % 2 == 1), indent=64))
        holder.Children.Add(sub)

        def toggle(sender, args, lid=lid, sub=sub, chev=chev):
            if sub.Visibility == Visibility.Visible:
                sub.Visibility = Visibility.Collapsed
                chev.Text = CHEV_CLOSED
                self.expanded.discard(lid)
            else:
                sub.Visibility = Visibility.Visible
                chev.Text = CHEV_OPEN
                self.expanded.add(lid)
        row.MouseLeftButtonUp += toggle
        return holder

    def note_row(self, text):
        return tb(text, 12, False, MUTED, margin=Thickness(70, 6, 6, 6))

    def instance_cells(self, r, d):
        cb = self.make_checkbox(d["id"] in self.selected_insts)
        cb.Checked += self.make_inst_handler(r, d)
        cb.Unchecked += self.make_inst_handler(r, d)
        self.inst_cbs[r["id"]].append((d["id"], cb))

        btn = Button()
        btn.Style = self.FindResource("RedBtn" if d["pinned"] else "OutlineBtn")
        btn.Content = "Unpin" if d["pinned"] else "Pin"
        btn.Padding = Thickness(10, 2, 10, 2)
        btn.Margin = Thickness(4, 0, 0, 0)

        def click(sender, args, d=d):
            self.pin_instances([d["inst"]], not d["pinned"],
                               "unpin instance" if d["pinned"] else "pin instance")
        btn.Click += click
        level = (u"\u2248 " + d["level"]) if d["level_approx"] else d["level"]
        return [cb, d["name"], "Pinned" if d["pinned"] else "Not pinned", d["shared_txt"],
                d["shared_loc"], d["xyz"], d["rot"], d["workset"], level, btn]

    # -- filters ------------------------------------------------------------
    def on_filter_changed(self, sender, args):
        if self._loading:
            return
        self.render()

    def on_clear_filter(self, sender, args):
        self._loading = True
        try:
            self.TxtSearch.Text = u""
            self.ChkUnpinned.IsChecked = False
            self.ChkProblems.IsChecked = False
            self.CbSite.SelectedIndex = 0
        finally:
            self._loading = False
        self.render()

    # -- selection ----------------------------------------------------------
    def make_link_handler(self, r):
        def handler(sender, args):
            if self._syncing:
                return
            want = bool(sender.IsChecked)
            self._syncing = True
            try:
                if want:
                    self.selected_links.add(r["id"])
                else:
                    self.selected_links.discard(r["id"])
                for d in r["idata"]:
                    if want:
                        self.selected_insts.add(d["id"])
                    else:
                        self.selected_insts.discard(d["id"])
                for iid, icb in self.inst_cbs.get(r["id"], []):
                    icb.IsChecked = want
            finally:
                self._syncing = False
            self.sync_select_state()
        return handler

    def make_inst_handler(self, r, d):
        def handler(sender, args):
            if self._syncing:
                return
            if sender.IsChecked:
                self.selected_insts.add(d["id"])
            else:
                self.selected_insts.discard(d["id"])
            all_sel = all(x["id"] in self.selected_insts for x in r["idata"])
            self._syncing = True
            try:
                if all_sel:
                    self.selected_links.add(r["id"])
                else:
                    self.selected_links.discard(r["id"])
                lcb = self.link_cbs.get(r["id"])
                if lcb is not None:
                    lcb.IsChecked = all_sel
            finally:
                self._syncing = False
            self.sync_select_state()
        return handler

    def selection_items(self):
        """[(row, [selected instance data])] for every link touched by the selection."""
        items = []
        for r in self.rows:
            sel = [d for d in r["idata"] if d["id"] in self.selected_insts]
            if sel or (not r["idata"] and r["id"] in self.selected_links):
                items.append((r, sel))
        return items

    def sync_select_state(self):
        self._syncing = True
        try:
            items = self.selection_items()
            n_links = len(items)
            n_inst = len(self.selected_insts)
            shown = self.visible_rows()
            self.SelectAll.IsChecked = bool(shown) and all(r["id"] in self.selected_links for r in shown)
            self.BtnPinSel.Content = "Pin selected ({})".format(n_inst)
            self.BtnUnpinSel.Content = "Unpin selected ({})".format(n_inst)
            self.BtnPinSel.IsEnabled = n_inst > 0
            self.BtnUnpinSel.IsEnabled = n_inst > 0
            self.BtnReloadSel.Content = "Reload selected ({})".format(n_links)
            self.BtnReloadSel.IsEnabled = n_links > 0
            self.BtnCopy.Content = "Copy to model... ({})".format(n_links) if n_links else "Copy to model..."
            self.BtnCopy.IsEnabled = n_links > 0
            for b in (self.BtnUnload, self.BtnRemove, self.BtnOverlay, self.BtnAttachment,
                      self.BtnRoomOn, self.BtnRoomOff):
                b.IsEnabled = n_links > 0
            self.BtnSelectRevit.IsEnabled = n_inst > 0
            self.BtnExport.IsEnabled = bool(self.rows)
            self.BtnReloadAll.IsEnabled = bool(self.rows)
            self.BtnPinAll.IsEnabled = bool(self.rows)
            self.BtnUnpinAll.IsEnabled = bool(self.rows)
        finally:
            self._syncing = False

    def on_select_all(self, sender, args):
        want = bool(self.SelectAll.IsChecked)
        self._syncing = True
        try:
            for r in self.visible_rows():
                if want:
                    self.selected_links.add(r["id"])
                else:
                    self.selected_links.discard(r["id"])
                for d in r["idata"]:
                    if want:
                        self.selected_insts.add(d["id"])
                    else:
                        self.selected_insts.discard(d["id"])
            for cb in self.link_cbs.values():
                cb.IsChecked = want
            for lst in self.inst_cbs.values():
                for iid, icb in lst:
                    icb.IsChecked = want
        finally:
            self._syncing = False
        self.sync_select_state()

    def selected_rows(self):
        return [r for r, sel in self.selection_items()]

    def selected_instances(self):
        return [d["inst"] for r, sel in self.selection_items() for d in sel]

    def all_instances(self):
        return [d["inst"] for r in self.rows for d in r["idata"]]

    def progress(self, label):
        def cb(idx, total, name):
            self.StatusText.Text = u"{} {} of {}:  {}".format(label, idx + 1, total, name)
            doevents()
        return cb

    # -- pin / unpin --------------------------------------------------------
    def pin_instances(self, instances, flag, label):
        if not instances:
            emperor_ui.alert("There are no link instances to change.", title="Link Manager")
            return
        self.StatusText.Text = "Working..."
        doevents()
        try:
            ok, failed = ops.pin_instances(instances, flag, label)
        except Exception as ex:
            emperor_ui.alert("The operation failed and was rolled back.\n\n{}".format(ex),
                        title="Link Manager")
            self.reload("Failed")
            return
        msg = "{} {}".format("Pinned" if flag else "Unpinned", plural(ok, "instance"))
        if failed:
            msg += "  {}  {} failed".format(DOT, len(failed))
        self.reload(msg)
        if failed:
            emperor_ui.alert("Some instances could not be changed:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def on_pin_selected(self, sender, args):
        self.pin_instances(self.selected_instances(), True, "pin selected")

    def on_unpin_selected(self, sender, args):
        self.pin_instances(self.selected_instances(), False, "unpin selected")

    def on_pin_all(self, sender, args):
        self.pin_instances(self.all_instances(), True, "pin all links")

    def on_unpin_all(self, sender, args):
        self.pin_instances(self.all_instances(), False, "unpin all links")

    # -- reload / unload / remove / reference type ---------------------------
    def reload_links(self, rows, label):
        if not rows:
            return
        ok, failed = ops.reload_links(rows, self.progress("Reloading"))
        self.reload("{}: {} reloaded".format(label, ok) +
                    ("  {}  {} failed".format(DOT, len(failed)) if failed else ""))
        if failed:
            emperor_ui.alert("Some links could not be reloaded:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def on_reload_all(self, sender, args):
        self.reload_links(self.rows, "Reload all")

    def on_reload_selected(self, sender, args):
        self.reload_links(self.selected_rows(), "Reload selected")

    def on_unload(self, sender, args):
        rows = self.selected_rows()
        if not rows:
            return
        ok, failed, skipped = ops.unload_links(rows, self.progress("Unloading"))
        msg = "Unloaded {}".format(plural(ok, "link"))
        if skipped:
            msg += "  {}  {} already unloaded".format(DOT, skipped)
        if failed:
            msg += "  {}  {} failed".format(DOT, len(failed))
        self.reload(msg)
        if failed:
            emperor_ui.alert("Some links could not be unloaded:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def on_remove(self, sender, args):
        rows = [r for r in self.rows if r["id"] in self.selected_links]
        if not rows:
            emperor_ui.alert("Tick the link itself (not only some of its instances) to remove it.",
                        title="Link Manager")
            return
        n_inst = sum(len(r["idata"]) for r in rows)
        names = u"\n".join(u"   " + r["name"] for r in rows[:12])
        if len(rows) > 12:
            names += u"\n   ... and {} more".format(len(rows) - 12)
        if not emperor_ui.alert(u"Remove {} and their {} from this project?\n\n{}\n\n"
                           u"This can be undone with Ctrl+Z in Revit.".format(
                               plural(len(rows), u"link"), plural(n_inst, u"instance"), names),
                           title="Link Manager  {}  Remove links".format(DOT), yes=True, no=True):
            return
        try:
            ok, failed = ops.remove_links(rows)
        except Exception as ex:
            emperor_ui.alert("The removal failed and was rolled back.\n\n{}".format(ex), title="Link Manager")
            self.reload("Failed")
            return
        self.reload("Removed {}".format(plural(ok, "link")) +
                    ("  {}  {} failed".format(DOT, len(failed)) if failed else ""))
        if failed:
            emperor_ui.alert("Some links could not be removed:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def set_reference_type(self, overlay):
        rows = self.selected_rows()
        if not rows:
            return
        try:
            ok, failed, skipped = ops.set_reference_type(rows, overlay)
        except Exception as ex:
            emperor_ui.alert("The change failed and was rolled back.\n\n{}".format(ex), title="Link Manager")
            self.reload("Failed")
            return
        self.reload("{} set for {}".format("Overlay" if overlay else "Attachment", plural(ok, "link")) +
                    ("  {}  {} already so".format(DOT, skipped) if skipped else "") +
                    ("  {}  {} failed".format(DOT, len(failed)) if failed else ""))
        if failed:
            emperor_ui.alert("Some links could not be changed:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def set_room_bounding(self, rows, flag):
        if not rows:
            return
        self.StatusText.Text = "Working..."
        doevents()
        try:
            changed, failed, same = ops.set_room_bounding(rows, flag)
        except Exception as ex:
            emperor_ui.alert("The change failed and was rolled back.\n\n{}".format(ex), title="Link Manager")
            self.reload("Failed")
            return
        self.reload("Room Bounding {} for {}".format("ON" if flag else "OFF", plural(changed, "link")) +
                    ("  {}  {} already so".format(DOT, same) if same else "") +
                    ("  {}  {} failed".format(DOT, len(failed)) if failed else ""))
        if failed:
            emperor_ui.alert("Some links could not be changed:\n\n" + "\n".join(failed[:15]),
                        title="Link Manager")

    def make_room_handler(self, r):
        def handler(sender, args):
            self.set_room_bounding([r], bool(sender.IsChecked))
        return handler

    def on_room_on(self, sender, args):
        self.set_room_bounding(self.selected_rows(), True)

    def on_room_off(self, sender, args):
        self.set_room_bounding(self.selected_rows(), False)

    def on_overlay(self, sender, args):
        self.set_reference_type(True)

    def on_attachment(self, sender, args):
        self.set_reference_type(False)

    # -- select in Revit / export ---------------------------------------------
    def on_select_revit(self, sender, args):
        instances = self.selected_instances()
        if not instances:
            return
        try:
            ops.select_in_revit(instances)
        except Exception as ex:
            emperor_ui.alert("Could not select the instances.\n\n{}".format(ex), title="Link Manager")
            return
        self.Close()      # the window is modal: close it so the selection can be seen

    def on_export(self, sender, args):
        rows = self.visible_rows()
        if not rows:
            return
        dlg = SaveFileDialog()
        dlg.Filter = "CSV files (*.csv)|*.csv"
        dlg.FileName = "LinkManager_links.csv"
        dlg.Title = "Export the links shown in the table"
        if dlg.ShowDialog() != DialogResult.OK:
            return
        try:
            n = ops.export_csv(dlg.FileName, rows)
        except Exception as ex:
            emperor_ui.alert("Could not write the file.\n\n{}".format(ex), title="Link Manager")
            return
        self.StatusText.Text = u"Exported {} line{} to {}".format(n, u"" if n == 1 else u"s", dlg.FileName)

    # -- view buttons -------------------------------------------------------
    def on_refresh(self, sender, args):
        self.reload("Refreshed")

    def on_expand_all(self, sender, args):
        self.expanded = set(r["id"] for r in self.rows)
        self.render()

    def on_collapse_all(self, sender, args):
        self.expanded = set()
        self.render()

    def on_close(self, sender, args):
        self.Close()

    # -- linking ------------------------------------------------------------
    def on_link_files(self, sender, args):
        dlg = LinkFilesWindow()
        dlg.ShowDialog()
        if dlg.result and dlg.result["files"]:
            self.run_link(dlg.result)

    def run_link(self, opts):
        existing = set(r["name"].lower() for r in self.rows)
        results = []
        relative = opts["relative"]
        notes = []
        if relative and not doc.PathName:
            relative = False
            notes.append("The project is not saved yet, so absolute paths were used.")

        ws_enum = getattr(DB.WorksetConfigurationOption, opts["worksets"])
        files = opts["files"]
        for idx, path in enumerate(files):
            fname = os.path.basename(path)
            self.StatusText.Text = "Linking {} of {}:  {}".format(idx + 1, len(files), fname)
            doevents()
            if fname.lower() in existing:
                results.append((fname, False, "already linked, skipped"))
                continue
            if not os.path.exists(path):
                results.append((fname, False, "file not found"))
                continue
            results.append(self.link_one(path, fname, relative, opts, ws_enum))
            existing.add(fname.lower())

        done = [r for r in results if r[1]]
        self.reload("Linked {} of {} file{}".format(len(done), len(files), "" if len(files) == 1 else "s"))
        lines = []
        for name, ok, msg in results:
            lines.append(u"{}  {}  {}".format(u"\u2714" if ok else u"\u2718", name, msg))
        lines.extend(notes)
        if opts["placement"] == "Shared":
            lines.append("")
            lines.append("Shared placement: if Revit asks for a position (Location and Site), answer it "
                         "yourself; only 'Copy to model' answers it automatically.")
        emperor_ui.alert("\n".join(lines), title="Link Manager  {}  Result".format(DOT))

    def link_one(self, path, fname, relative, opts, ws_enum):
        t = DB.Transaction(doc, "Link Manager: link " + fname)
        try:
            t.Start()
            mp = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(path)
            lo = DB.RevitLinkOptions(relative, DB.WorksetConfiguration(ws_enum))
            res = DB.RevitLinkType.Create(doc, mp, lo)
            type_id = res.ElementId
            if type_id is None or eid(type_id) == -1:
                raise Exception("Revit could not load the model ({})".format(res.LoadResult))
            link_type = doc.GetElement(type_id)
            try:
                link_type.AttachmentType = (DB.AttachmentType.Overlay if opts["overlay"]
                                            else DB.AttachmentType.Attachment)
            except Exception:
                pass
            if opts.get("room_bounding"):
                try:
                    rp = room_bounding_param(link_type)
                    if rp is not None and not rp.IsReadOnly:
                        rp.Set(1)
                except Exception:
                    pass

            inst = None
            note = ""
            if opts["placement"] == "Shared":
                try:
                    inst = DB.RevitLinkInstance.Create(doc, type_id, DB.ImportPlacement.Shared)
                except Exception:
                    inst = None
                    note = "  (shared coordinates placement not possible, placed origin to origin)"
            if inst is None:
                inst = DB.RevitLinkInstance.Create(doc, type_id)
            if opts["pin"]:
                inst.Pinned = True
            t.Commit()
            return (fname, True, "linked" + (", pinned" if opts["pin"] else "") + note)
        except Exception as ex:
            try:
                t.RollBack()
            except Exception:
                pass
            return (fname, False, "failed: {}".format(ex))

    # -- copy links to other open models --------------------------------------
    def on_copy(self, sender, args):
        items = self.selection_items()
        if not items:
            emperor_ui.alert("Select at least one link or instance first.", title="Link Manager")
            return
        targets = open_target_models()
        if not targets:
            emperor_ui.alert("There is no other project open in this Revit session.\n\n"
                        "Open the target model first (it does not need to be the active one), "
                        "then press Copy to model again.", title="Link Manager")
            return
        pick = PickModelWindow(targets)
        pick.ShowDialog()
        tdocs = pick.result
        if not tdocs:
            return
        self.StatusText.Text = "Preparing the preview..."
        doevents()
        preview = build_preview(items, tdocs)
        options = CopyOptionsWindow(tdocs, items, preview)
        options.ShowDialog()
        if not options.accepted:
            self.StatusText.Text = "Ready"
            return
        self.copy_to_models(items, tdocs, options.unshared_exact, options.policy)

    def copy_to_models(self, items, tdocs, unshared_exact, policy):
        reset_copy_state()
        lines = []
        total_done = 0
        total_links = 0
        for ti, tdoc in enumerate(tdocs):
            label = u"Copying to {} ({}/{})".format(tdoc.Title, ti + 1, len(tdocs))

            def progress(idx, total, name, label=label):
                self.StatusText.Text = u"{}:  link {} of {}  {}".format(label, idx + 1, total, name)
                doevents()
            results = copy_items_to_target(tdoc, items, unshared_exact, policy, progress)
            done = len([x for x in results if x[1]])
            total_done += done
            total_links += len(results)
            lines.append(u"== {} ==".format(tdoc.Title))
            for name, ok, msg in results:
                lines.append(u"{}  {}  {}".format(u"\u2714" if ok else u"\u2718", name, msg))
            lines.append(u"")

        self.reload(u"Copied {} of {} link{} into {}".format(
            total_done, total_links, u"" if total_links == 1 else u"s", plural(len(tdocs), u"model")))
        if COPY_STATE["site_mismatch"]:
            lines.append("Some instances could not be verified as both shared-positioned and associated "
                         "with the source's named shared site. Check each instance's note above. "
                         "Revit's API has no supported setter for an instance's named shared site, so "
                         "the tool will not fake it by writing a parameter or publishing coordinates. "
                         "For any instance that needs it: select it > Properties > Shared Site > "
                         "'Move instance to' the intended site. Never use 'Record current position as'.")
            lines.append("")
        if COPY_STATE["saveable"]:
            lines.append("When you save a target, Revit may ask to save shared positions back to the "
                         "linked files: choose Do not save.")
            lines.append("")
        if COPY_STATE["picks"]:
            ok_n = len([x for x in COPY_STATE["picks"]
                        if x[1].startswith((u"selected", u"physically selected"))])
            lines.append(u"Revit asked for a position {} time{}; {} answered automatically with the "
                         u"source shared site.".format(len(COPY_STATE["picks"]),
                                                       u"" if len(COPY_STATE["picks"]) == 1 else u"s", ok_n))
            for nm, res in COPY_STATE["picks"]:
                if not res.startswith((u"selected", u"physically selected")):
                    lines.append(u"   {}: {}".format(nm, res))
            lines.append(u"Details: %TEMP%\\LinkManager_dialogs.log")
            lines.append(u"")
        lines.append(u"No coordinates were published to any linked file.")
        lines.append(u"The target model{} stay{} open and NOT saved: review, then save or synchronize.".format(
            u"s" if len(tdocs) > 1 else u"", u"" if len(tdocs) > 1 else u"s"))
        lines.append(u"Each target has the whole copy as ONE undo step (Ctrl+Z in that model).")
        emperor_ui.alert(u"\n".join(lines), title=u"Link Manager  {}  Copy result".format(DOT))


# ----------------------------------------------------------------------------
if doc.IsFamilyDocument:
    emperor_ui.alert("Open a project to use the Link Manager.", title="Link Manager")
else:
    LinkManagerWindow().ShowDialog()
