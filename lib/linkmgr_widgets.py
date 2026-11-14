# -*- coding: utf-8 -*-
"""Red / white WPF building blocks used by the Link Manager windows."""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import System
from System.Windows import (Thickness, CornerRadius, VerticalAlignment, TextWrapping, FontWeights)
from System.Windows.Controls import Border, StackPanel, TextBlock, TextBox
from System.Windows.Media import SolidColorBrush, ColorConverter, Brushes

from linkmgr_common import DASH


def brush(hex_color):
    return SolidColorBrush(ColorConverter.ConvertFromString(hex_color))


RED = brush("#8B111C")
RED_DARK = brush("#6E0C16")
TINT = brush("#FBF6F7")
LINE = brush("#EADFE0")
INK = brush("#303034")
MUTED = brush("#77777D")
GREY_LINE = brush("#D8CBCD")
HOVER = brush("#F7EBEC")
BAD_ROW = brush("#F8D7D3")
WHITE = Brushes.White


def tb(text, size=13, bold=False, fg=None, wrap=False, margin=None):
    t = TextBlock()
    t.Text = text
    t.FontSize = size
    t.Foreground = fg if fg is not None else INK
    if bold:
        t.FontWeight = FontWeights.SemiBold
    if wrap:
        t.TextWrapping = TextWrapping.Wrap
    if margin is not None:
        t.Margin = margin
    return t


def badge(text, filled=False, muted=False):
    b = Border()
    b.CornerRadius = CornerRadius(10)
    b.Padding = Thickness(9, 2, 9, 2)
    b.Margin = Thickness(6, 0, 0, 0)
    b.BorderThickness = Thickness(1)
    if filled:
        b.Background, b.BorderBrush, fg = RED, RED, WHITE
    elif muted:
        b.Background, b.BorderBrush, fg = WHITE, GREY_LINE, MUTED
    else:
        b.Background, b.BorderBrush, fg = WHITE, RED, RED
    b.Child = tb(text, 11, True, fg)
    return b


def field(label, value, width=200):
    sp = StackPanel()
    sp.Width = width
    sp.Margin = Thickness(0, 0, 14, 8)
    sp.Children.Add(tb(label.upper(), 10, True, MUTED))
    sp.Children.Add(tb(value if value else DASH, 12.5, False, INK, wrap=True))
    return sp


def path_row(label, value):
    sp = StackPanel()
    sp.Margin = Thickness(0, 0, 0, 8)
    sp.Children.Add(tb(label.upper(), 10, True, MUTED))
    box = TextBox()
    box.Text = value if value else DASH
    box.IsReadOnly = True
    box.BorderThickness = Thickness(0)
    box.Background = Brushes.Transparent
    box.TextWrapping = TextWrapping.Wrap
    box.FontSize = 12.5
    box.Foreground = INK
    box.Padding = Thickness(0)
    sp.Children.Add(box)
    return sp


def table_row(cols, cells, header=False, alt=False, indent=0, bad=False):
    """One table row. cells: strings, or UIElements (checkbox, button, ...). cols: (header, width)."""
    border = Border()
    border.BorderBrush = LINE
    border.BorderThickness = Thickness(0, 0, 0, 1)
    border.Padding = Thickness(indent, 6, 0, 6)
    border.Background = RED if header else (BAD_ROW if bad else (TINT if alt else WHITE))
    g = System.Windows.Controls.Grid()
    for col in cols:
        cd = System.Windows.Controls.ColumnDefinition()
        cd.Width = System.Windows.GridLength(col[1])
        g.ColumnDefinitions.Add(cd)
    for i, cell in enumerate(cells):
        if not isinstance(cell, System.Windows.UIElement):
            el = tb(cell if (cell or header) else DASH, 12 if header else 12.5, header,
                    WHITE if header else INK)
            el.TextTrimming = System.Windows.TextTrimming.CharacterEllipsis
            el.ToolTip = cell
            el.Margin = Thickness(6, 0, 6, 0)
            el.VerticalAlignment = VerticalAlignment.Center
        else:
            el = cell
        System.Windows.Controls.Grid.SetColumn(el, i)
        g.Children.Add(el)
    border.Child = g
    if not header:
        _hover(border)
    return border


def _hover(border):
    """Row reacts to the mouse: light red tint and a red left edge while the pointer is on it."""
    def enter(sender, args):
        try:
            sender.Tag = sender.Background
            sender.Background = HOVER
        except Exception:
            pass

    def leave(sender, args):
        try:
            if sender.Tag is not None:
                sender.Background = sender.Tag
        except Exception:
            pass
    border.MouseEnter += enter
    border.MouseLeave += leave
