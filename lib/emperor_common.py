# -*- coding: ascii -*-
# Emperor BIM Toolkit for Revit / pyRevit IronPython 2.7
# Author: Yahya Morcy

import os
import sys
import json
import time
import traceback
import codecs
import re

import clr
clr.AddReference('RevitAPI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System')
clr.AddReference('System.Data')
clr.AddReference('System.Windows.Forms')

# IMPORTANT: import the Revit DB namespace FIRST. It contains classes named
# Color and Grid that would otherwise overwrite the WPF Color / Grid classes
# imported below and break every window.
from Autodesk.Revit.DB import *

import System
from System import Uri, Guid, UriKind
from System.IO import File, Directory, Path
from System.Data import DataTable, DataColumn
from System.Windows import Window, Thickness, HorizontalAlignment, VerticalAlignment, WindowStartupLocation, ResizeMode, FontWeights, TextWrapping
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Media import Color, SolidColorBrush, FontFamily
from System.Windows.Media.Imaging import BitmapImage
from System.Windows.Controls import (Grid, RowDefinition, ColumnDefinition, StackPanel,
    DockPanel, Border, TextBlock, TextBox, Button, Image, ComboBox, DataGrid,
    CheckBox, Label, ListBox, ScrollViewer, Orientation, SelectionMode,
    ScrollBarVisibility, TabControl, TabItem, WrapPanel, RadioButton, ProgressBar,
    ContextMenu, MenuItem, Separator, Expander)
from System.Windows.Input import Cursors
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage, Visibility
from Microsoft.Win32 import OpenFileDialog, SaveFileDialog
from System.Windows.Forms import FolderBrowserDialog, DialogResult

EXT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ASSET_DIR = os.path.join(EXT_ROOT, 'lib', 'assets')
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'EmperorBIMToolkit')
if not os.path.isdir(APPDATA_DIR):
    try:
        os.makedirs(APPDATA_DIR)
    except:
        pass
LOG_PATH = os.path.join(APPDATA_DIR, 'EmperorBIMToolkit.log')
RED = '#8B111C'
RED2 = '#B32330'
INK = '#303034'
GRAY = '#77777D'
LIGHT = '#F7EFF0'
WHITE = '#FFFFFF'
BORDER = '#D8CBCD'
GREEN = '#327D50'


def _log(message):
    try:
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with codecs.open(LOG_PATH, 'a', 'utf-8') as fp:
            fp.write(u'{0} | {1}\n'.format(stamp, _u(message)))
    except:
        pass


def _u(value):
    try:
        if value is None:
            return u''
        if isinstance(value, unicode):
            return value
    except NameError:
        pass
    try:
        return unicode(value)
    except NameError:
        try:
            return str(value)
        except:
            return u''
    except:
        try:
            return str(value)
        except:
            return u''


def _brush(hex_color):
    h = hex_color.replace('#', '')
    if len(h) == 8:
        a = int(h[0:2], 16); r = int(h[2:4], 16); g = int(h[4:6], 16); b = int(h[6:8], 16)
        return SolidColorBrush(Color.FromArgb(a, r, g, b))
    return SolidColorBrush(Color.FromRgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))


def _icon_path(name, dark=False):
    suffix = '.dark.png' if dark else '.png'
    p = os.path.join(ASSET_DIR, name + suffix)
    if not os.path.exists(p):
        p = os.path.join(ASSET_DIR, 'settings.png')
    return p


def _image(name, width=20, height=20, dark=False):
    img = Image()
    img.Width = width
    img.Height = height
    img.Margin = Thickness(0, 0, 7, 0)
    try:
        img.Source = BitmapImage(Uri(_icon_path(name, dark), UriKind.Absolute))
    except:
        pass
    return img


def _text(text, size=13, color=INK, bold=False, wrap=False):
    t = TextBlock()
    t.Text = _u(text)
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = size
    t.Foreground = _brush(color)
    t.FontWeight = FontWeights.Bold if bold else FontWeights.Normal
    t.TextWrapping = TextWrapping.Wrap if wrap else TextWrapping.NoWrap
    t.Margin = Thickness(0, 1, 0, 1)
    return t


def _safe_handler(callback):
    # Exceptions raised inside WPF event handlers can take Revit down with them.
    # Catch everything, log it and show it instead.
    def handler(sender, args):
        try:
            callback()
        except Exception as ex:
            _log('Unhandled error: {0}\n{1}'.format(ex, traceback.format_exc()))
            _show_message('Unexpected error:\n\n{0}\n\nDetails were written to:\n{1}'.format(_u(ex), LOG_PATH), error=True)
    return handler


# ================================================================ theme (v3.1)
# Interactive WPF styles (hover / pressed / focus / disabled) parsed from XAML.
# If anything fails the plain controls are used, so the tool still opens.

_THEME_XAML = u'''
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

  <!--BTN-->
  <Style x:Key="EkButton" TargetType="Button">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="Button">
          <Grid x:Name="root" RenderTransformOrigin="0.5,0.5">
            <Grid.RenderTransform><ScaleTransform x:Name="sc" ScaleX="1" ScaleY="1"/></Grid.RenderTransform>
            <Border x:Name="bd" CornerRadius="5" Background="{TemplateBinding Background}"
                    BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}"/>
            <Border x:Name="hv" CornerRadius="5" Background="@HOVER_BG@" BorderBrush="@HOVER_BORDER@"
                    BorderThickness="1" Opacity="0" IsHitTestVisible="False"/>
            <Border x:Name="EmperorGlow" CornerRadius="5" Opacity="0" IsHitTestVisible="False" Tag="@GLOW@"/>
            <Border x:Name="pr" CornerRadius="5" Background="@PRESS_BG@" BorderBrush="@HOVER_BORDER@"
                    BorderThickness="1" Opacity="0" IsHitTestVisible="False"/>
            <ContentPresenter Margin="{TemplateBinding Padding}" HorizontalAlignment="Center"
                              VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Trigger.EnterActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.12"/>
                <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.15"/>
              </Storyboard></BeginStoryboard></Trigger.EnterActions>
              <Trigger.ExitActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.18"/>
                <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.25"/>
              </Storyboard></BeginStoryboard></Trigger.ExitActions>
            </Trigger>
            <Trigger Property="IsPressed" Value="True">
              <Trigger.EnterActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="pr" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.05"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleX" To="0.97" Duration="0:0:0.06"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleY" To="0.94" Duration="0:0:0.06"/>
              </Storyboard></BeginStoryboard></Trigger.EnterActions>
              <Trigger.ExitActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="pr" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.12"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleX" To="1" Duration="0:0:0.1"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleY" To="1" Duration="0:0:0.1"/>
              </Storyboard></BeginStoryboard></Trigger.ExitActions>
            </Trigger>
            <Trigger Property="IsKeyboardFocused" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="bd" Property="BorderThickness" Value="2"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="root" Property="Opacity" Value="0.4"/>
              <Setter Property="Cursor" Value="Arrow"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <!--/BTN-->

  <Style TargetType="TabItem">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="TabItem">
          <Border x:Name="bd" Background="Transparent" BorderBrush="Transparent" BorderThickness="0,0,0,3"
                  Padding="20,8,20,6" Margin="0,0,2,0">
            <ContentPresenter x:Name="cp" ContentSource="Header" TextElement.Foreground="@GRAY@"
                              TextElement.FontWeight="Normal" HorizontalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="bd" Property="Background" Value="@LIGHT@"/>
              <Setter TargetName="cp" Property="TextElement.Foreground" Value="@RED@"/>
            </Trigger>
            <Trigger Property="IsSelected" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED@"/>
              <Setter TargetName="bd" Property="Background" Value="@WHITE@"/>
              <Setter TargetName="cp" Property="TextElement.Foreground" Value="@RED@"/>
              <Setter TargetName="cp" Property="TextElement.FontWeight" Value="Bold"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="ListBoxItem">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Padding" Value="4,3,4,3"/>
    <Setter Property="Margin" Value="0,1,0,1"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="ListBoxItem">
          <Border x:Name="bd" CornerRadius="5" Background="Transparent" BorderBrush="Transparent"
                  BorderThickness="1" Padding="{TemplateBinding Padding}">
            <ContentPresenter/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="bd" Property="Background" Value="@LIGHT@"/>
              <Setter TargetName="bd" Property="BorderBrush" Value="@BORDER@"/>
            </Trigger>
            <Trigger Property="IsSelected" Value="True">
              <Setter TargetName="bd" Property="Background" Value="@SELECT@"/>
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED2@"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="CheckBox">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="CheckBox">
          <StackPanel x:Name="root" Orientation="Horizontal" Background="Transparent">
            <Grid Width="17" Height="17" VerticalAlignment="Center">
              <Border x:Name="box" CornerRadius="4" BorderThickness="1.5" BorderBrush="@GRAY@" Background="@WHITE@"/>
              <Path x:Name="tick" Data="M4,8.8 L7,11.8 L13,5" Stroke="White" StrokeThickness="2"
                    StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Visibility="Collapsed"/>
            </Grid>
            <ContentPresenter Margin="7,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </StackPanel>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="box" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="box" Property="Background" Value="@LIGHT@"/>
            </Trigger>
            <Trigger Property="IsChecked" Value="True">
              <Setter TargetName="box" Property="Background" Value="@RED@"/>
              <Setter TargetName="box" Property="BorderBrush" Value="@RED@"/>
              <Setter TargetName="tick" Property="Visibility" Value="Visible"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="root" Property="Opacity" Value="0.45"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="RadioButton">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="RadioButton">
          <StackPanel x:Name="root" Orientation="Horizontal" Background="Transparent">
            <Grid Width="17" Height="17" VerticalAlignment="Center">
              <Ellipse x:Name="ring" StrokeThickness="1.5" Stroke="@GRAY@" Fill="@WHITE@"/>
              <Ellipse x:Name="dot" Width="9" Height="9" Fill="@RED@" Visibility="Collapsed"/>
            </Grid>
            <ContentPresenter Margin="7,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </StackPanel>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="ring" Property="Stroke" Value="@RED2@"/>
              <Setter TargetName="ring" Property="Fill" Value="@LIGHT@"/>
            </Trigger>
            <Trigger Property="IsChecked" Value="True">
              <Setter TargetName="ring" Property="Stroke" Value="@RED@"/>
              <Setter TargetName="dot" Property="Visibility" Value="Visible"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="root" Property="Opacity" Value="0.45"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="EkTextBox" TargetType="TextBox">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="TextBox">
          <Border x:Name="bd" CornerRadius="4" Background="{TemplateBinding Background}"
                  BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="1">
            <ScrollViewer x:Name="PART_ContentHost" Margin="{TemplateBinding Padding}" VerticalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@GRAY@"/>
            </Trigger>
            <Trigger Property="IsKeyboardFocused" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="bd" Property="BorderThickness" Value="2"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="bd" Property="Opacity" Value="0.5"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="DataGridColumnHeader">
    <Setter Property="Background" Value="@LIGHT@"/>
    <Setter Property="Foreground" Value="@RED@"/>
    <Setter Property="FontWeight" Value="SemiBold"/>
    <Setter Property="Padding" Value="8,6,8,6"/>
    <Setter Property="BorderBrush" Value="@BORDER@"/>
    <Setter Property="BorderThickness" Value="0,0,1,2"/>
    <Style.Triggers>
      <Trigger Property="IsMouseOver" Value="True">
        <Setter Property="Background" Value="@SELECT@"/>
      </Trigger>
    </Style.Triggers>
  </Style>

  <Style TargetType="DataGridCell">
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Padding" Value="4,2,4,2"/>
    <Style.Triggers>
      <DataTrigger Binding="{Binding RelativeSource={RelativeSource AncestorType=DataGridRow}, Path=IsMouseOver}" Value="True">
        <Setter Property="Background" Value="@HOVERROW@"/>
      </DataTrigger>
      <Trigger Property="IsSelected" Value="True">
        <Setter Property="Background" Value="@SELECT@"/>
        <Setter Property="Foreground" Value="@INK@"/>
        <Setter Property="BorderBrush" Value="Transparent"/>
      </Trigger>
    </Style.Triggers>
  </Style>

  <Style TargetType="DataGridRow">
    <Setter Property="MinHeight" Value="26"/>
  </Style>
</ResourceDictionary>
'''

_THEME_CACHE = {}


def _glow(win):
    """Emperor mouse-following glow on the buttons of this window (emperor_ui)."""
    try:
        import emperor_ui
        emperor_ui.add_extras(win)          # drop-downs, menus, expanders, tooltips
        emperor_ui.enable_mouse_glow(win)
    except Exception as ex:
        _log('Mouse glow not attached: {0}'.format(ex))


def _theme():
    """Returns the shared ResourceDictionary, or None when styling is unavailable."""
    if 'dict' in _THEME_CACHE:
        return _THEME_CACHE['dict']
    result = None
    try:
        from System.IO import StringReader
        from System.Windows.Markup import XamlReader
        xaml = _THEME_XAML
        start = xaml.index(u'<!--BTN-->'); end = xaml.index(u'<!--/BTN-->')
        block = xaml[start + 10:end]
        normal = block.replace(u'@GLOW@', u'#33B32330').replace(u'@HOVER_BG@', u'#F7EBEC').replace(u'@PRESS_BG@', u'#E8CDD1')
        primary = (block.replace(u'x:Key="EkButton"', u'x:Key="EkPrimaryButton"')
                   .replace(u'@GLOW@', u'#55FFFFFF').replace(u'@HOVER_BG@', u'#33FFFFFF').replace(u'@PRESS_BG@', u'#33000000'))
        xaml = xaml[:start] + normal + primary + xaml[end + 11:]
        values = {
            'RED': RED, 'RED2': RED2, 'INK': INK, 'GRAY': GRAY, 'LIGHT': LIGHT, 'WHITE': WHITE,
            'BORDER': BORDER, 'SELECT': '#F3DADD', 'HOVERROW': '#FAF1F2', 'HOVER_BORDER': RED2}
        for key in values:
            xaml = xaml.replace(u'@' + key + u'@', values[key])
        result = XamlReader.Parse(xaml)
    except Exception as ex:
        _log('Theme could not be loaded, using plain controls: {0}\n{1}'.format(ex, traceback.format_exc()))
        result = None
    _THEME_CACHE['dict'] = result
    return result


def _apply_style(control, key):
    try:
        theme = _theme()
        if theme is not None and theme.Contains(key):
            control.Style = theme[key]
            return True
    except Exception as ex:
        _log('Style {0} not applied: {1}'.format(key, ex))
    return False


def _button(label, icon, callback, primary=False, min_width=0):
    b = Button()
    b.Margin = Thickness(3, 3, 3, 3)
    b.Padding = Thickness(10, 6, 10, 6)
    b.MinHeight = 34
    b.MinWidth = min_width
    b.Cursor = Cursors.Hand
    b.BorderThickness = Thickness(1)
    b.BorderBrush = _brush(RED if primary else BORDER)
    b.Background = _brush(RED if primary else WHITE)
    b.Foreground = _brush(WHITE if primary else RED)
    b.FontFamily = FontFamily('Segoe UI')
    b.FontSize = 12
    sp = StackPanel()
    sp.Orientation = Orientation.Horizontal
    sp.VerticalAlignment = VerticalAlignment.Center
    if icon:
        sp.Children.Add(_image(icon, 18, 18, primary))    # white icon on red buttons, red icon on white ones
    t = _text(label, 12, WHITE if primary else RED, primary)
    if not primary:
        try:
            t.FontWeight = FontWeights.SemiBold
        except Exception:
            pass
    t.VerticalAlignment = VerticalAlignment.Center
    sp.Children.Add(t)
    b.Content = sp
    if callback:
        b.Click += _safe_handler(callback)
    styled = False
    try:
        import emperor_ui                       # same button style as every other Emperor window
        d = emperor_ui.dictionary()
        if d is not None:
            b.Style = d['RedBtn' if primary else 'OutlineBtn']
            b.Padding = Thickness(12, 5, 12, 5)
            styled = True
    except Exception:
        styled = False
    if not styled:
        _apply_style(b, 'EkPrimaryButton' if primary else 'EkButton')
    return b


def _label(text, width=None):
    t = Label()
    t.Content = _u(text)
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = 12
    t.Foreground = _brush(INK)
    t.Padding = Thickness(2, 4, 6, 2)
    if width is not None:
        t.Width = width
    return t


def _textbox(value='', width=None, height=29):
    t = TextBox()
    t.Text = _u(value)
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = 12
    t.Padding = Thickness(7, 0, 7, 0)          # no vertical padding: the text is centred and never clipped
    t.Margin = Thickness(3, 3, 3, 3)
    t.Height = height
    t.VerticalContentAlignment = VerticalAlignment.Center
    t.BorderBrush = _brush(BORDER)
    t.Background = _brush(WHITE)
    if width is not None:
        t.Width = width
    _apply_style(t, 'EkTextBox')
    return t


def _combo(items, selected_index=0, width=None):
    c = ComboBox()
    c.FontFamily = FontFamily('Segoe UI')
    c.FontSize = 12
    c.Margin = Thickness(3, 3, 3, 3)
    c.Padding = Thickness(5, 3, 5, 3)
    c.Height = 30
    c.BorderBrush = _brush(BORDER)
    c.Background = _brush(WHITE)
    for item in items:
        c.Items.Add(_u(item))
    if c.Items.Count:
        c.SelectedIndex = max(0, min(selected_index, c.Items.Count - 1))
    if width is not None:
        c.Width = width
    return c


def _set_status(status, message, is_error=False):
    try:
        status.Text = _u(message)
        status.Foreground = _brush(RED2 if is_error else (GREEN if 'complete' in _u(message).lower() or 'ready' in _u(message).lower() else GRAY))
    except:
        pass


def _make_window(title, subtitle, width=1000, height=680, owner=None):
    win = Window()
    win.Title = title
    win.Width = width
    win.Height = height
    win.MinWidth = min(width, 760)
    win.MinHeight = min(height, 520)
    win.WindowStartupLocation = WindowStartupLocation.CenterOwner if owner else WindowStartupLocation.CenterScreen
    win.ResizeMode = ResizeMode.CanResize
    win.Background = _brush('#F8F8F8')
    _glow(win)
    win.FontFamily = FontFamily('Segoe UI')
    try:
        theme = _theme()
        if theme is not None:
            win.Resources.MergedDictionaries.Add(theme)
    except Exception as ex:
        _log('Theme not attached: {0}'.format(ex))
    if owner:
        try:
            win.Owner = owner
        except:
            pass
    else:
        try:
            from System.Diagnostics import Process
            WindowInteropHelper(win).Owner = Process.GetCurrentProcess().MainWindowHandle
        except:
            pass
    dock = DockPanel()
    dock.LastChildFill = True
    dock.Margin = Thickness(0)
    header = Border()
    try:
        from System.Windows.Media import LinearGradientBrush, GradientStop
        from System.Windows import Point
        gb = LinearGradientBrush()
        gb.StartPoint = Point(0, 0); gb.EndPoint = Point(1, 0)
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x6E, 0x0C, 0x16), 0.0))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x8B, 0x11, 0x1C), 0.55))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0xB3, 0x23, 0x30), 1.0))
        header.Background = gb
    except:
        header.Background = _brush(RED)
    header.BorderBrush = _brush('#E2B3B8')
    header.BorderThickness = Thickness(0, 0, 0, 2)
    header.Padding = Thickness(18, 12, 18, 12)
    hs = StackPanel()
    ht = _text(title, 19, WHITE, True)
    st = _text(subtitle, 11, '#F7DDE0', False, True)
    hs.Children.Add(ht); hs.Children.Add(st)
    header.Child = hs
    DockPanel.SetDock(header, System.Windows.Controls.Dock.Top)
    dock.Children.Add(header)
    toolbar = WrapPanel()
    toolbar.Orientation = Orientation.Horizontal
    toolbar.Background = _brush(WHITE)
    toolbar.Margin = Thickness(6, 4, 6, 2)
    toolbar.Margin = Thickness(0)
    toolbar.HorizontalAlignment = HorizontalAlignment.Stretch
    DockPanel.SetDock(toolbar, System.Windows.Controls.Dock.Top)
    dock.Children.Add(toolbar)
    status_border = Border()
    status_border.Background = _brush('#F3E9EA')
    status_border.BorderBrush = _brush(BORDER)
    status_border.BorderThickness = Thickness(0, 1, 0, 0)
    status_border.Padding = Thickness(10, 4, 10, 4)
    status = _text('Ready.', 11, GRAY, False)
    status_border.Child = status
    DockPanel.SetDock(status_border, System.Windows.Controls.Dock.Bottom)
    dock.Children.Add(status_border)
    footer = StackPanel()
    footer.Orientation = Orientation.Horizontal
    footer.HorizontalAlignment = HorizontalAlignment.Right
    footer.Background = _brush(WHITE)
    footer.Margin = Thickness(0, 0, 8, 0)
    DockPanel.SetDock(footer, System.Windows.Controls.Dock.Bottom)
    dock.Children.Add(footer)
    content_border = Border()
    content_border.Margin = Thickness(8)
    content_border.Background = _brush(WHITE)
    content_border.BorderBrush = _brush(BORDER)
    content_border.BorderThickness = Thickness(1)
    content_border.CornerRadius = System.Windows.CornerRadius(6)
    content_border.Padding = Thickness(8)
    content = Grid()
    content_border.Child = content
    dock.Children.Add(content_border)
    win.Content = dock
    return win, toolbar, content, status, footer


def _new_datatable(columns, rows=None):
    table = DataTable()
    for col in columns:
        if isinstance(col, tuple):
            table.Columns.Add(DataColumn(col[0], clr.GetClrType(col[1])))
        else:
            table.Columns.Add(DataColumn(col, clr.GetClrType(System.String)))
    if rows:
        for row in rows:
            dr = table.NewRow()
            for i, col in enumerate(columns):
                name = col[0] if isinstance(col, tuple) else col
                val = row.get(name, '') if isinstance(row, dict) else row[i]
                if val is None:
                    val = ''
                dr[name] = val
            table.Rows.Add(dr)
    return table


def _make_grid(table, editable=False, readonly_columns=None, can_add=False, hidden_columns=None):
    grid = DataGrid()
    grid.AutoGenerateColumns = True
    grid.IsReadOnly = not editable
    grid.CanUserAddRows = bool(can_add and editable)
    grid.CanUserDeleteRows = editable
    grid.CanUserResizeRows = True
    grid.SelectionUnit = System.Windows.Controls.DataGridSelectionUnit.FullRow
    grid.GridLinesVisibility = System.Windows.Controls.DataGridGridLinesVisibility.Horizontal
    grid.HeadersVisibility = System.Windows.Controls.DataGridHeadersVisibility.Column
    grid.RowBackground = _brush(WHITE)
    grid.AlternatingRowBackground = _brush('#FBF6F7')
    grid.BorderBrush = _brush(BORDER)
    grid.HorizontalGridLinesBrush = _brush('#EADFE0')
    grid.RowHeaderWidth = 0
    grid.FontFamily = FontFamily('Segoe UI')
    grid.FontSize = 12
    readonly_set = set([_u(x) for x in (readonly_columns or [])])
    hidden_set = set([_u(x) for x in (hidden_columns or [])])
    if readonly_set or hidden_set:
        def lock_generated_column(sender, args):
            header = _u(args.Column.Header)
            if header in readonly_set:
                args.Column.IsReadOnly = True
            if header in hidden_set:
                args.Column.Visibility = Visibility.Collapsed
        grid.AutoGeneratingColumn += lock_generated_column
    grid.ItemsSource = table.DefaultView
    return grid


def _pick_open_file(title='Select CSV file', filter_text='CSV files (*.csv)|*.csv|All files (*.*)|*.*'):
    dlg = OpenFileDialog()
    dlg.Title = title
    dlg.Filter = filter_text
    dlg.Multiselect = False
    try:
        if dlg.ShowDialog() == True:
            return dlg.FileName
    except:
        pass
    return None


def _pick_save_file(title='Save CSV file', default_name='EmperorToolkit.csv', filter_text='CSV files (*.csv)|*.csv|All files (*.*)|*.*'):
    dlg = SaveFileDialog()
    dlg.Title = title
    dlg.Filter = filter_text
    dlg.FileName = default_name
    dlg.AddExtension = True
    dlg.OverwritePrompt = True
    try:
        if dlg.ShowDialog() == True:
            return dlg.FileName
    except:
        pass
    return None


def _pick_folder(description='Select output folder'):
    dlg = FolderBrowserDialog()
    dlg.Description = description
    dlg.ShowNewFolderButton = True
    try:
        if dlg.ShowDialog() == DialogResult.OK:
            return dlg.SelectedPath
    except:
        pass
    return None


def _parse_csv_line(line, delimiter=u','):
    values = []
    current = []
    quoted = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if quoted and i + 1 < len(line) and line[i + 1] == '"':
                current.append('"'); i += 1
            else:
                quoted = not quoted
        elif ch == delimiter and not quoted:
            values.append(u''.join(current).strip() if not quoted else u''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    values.append(u''.join(current).strip() if not quoted else u''.join(current))
    if values and values[0].startswith(u'\ufeff'):
        values[0] = values[0].replace(u'\ufeff', u'', 1)
    return values


def _read_csv(path):
    # Excel saves CSV as UTF-8 or as ANSI, and uses ';' as separator in many regional
    # settings. Handle both instead of failing with an encoding error.
    text = None
    for enc in ('utf-8-sig', 'cp1256', 'cp1252'):
        try:
            with codecs.open(path, 'r', enc) as fp:
                text = fp.read()
            break
        except Exception:
            text = None
    if text is None:
        raise Exception('Could not read the CSV file (unsupported text encoding).')
    lines = text.replace(u'\r\n', u'\n').replace(u'\r', u'\n').split(u'\n')
    first = u''
    for line in lines:
        if line.strip():
            first = line
            break
    delimiter = u';' if first.count(u';') > first.count(u',') else u','
    if first.count(u'\t') > max(first.count(u';'), first.count(u',')):
        delimiter = u'\t'
    rows = []
    for line in lines:
        if not line.strip():
            continue
        rows.append(_parse_csv_line(line, delimiter))
    return rows


def _csv_escape(value):
    value = _u(value).replace('\r', ' ').replace('\n', ' ')
    if ',' in value or '"' in value or value.startswith(' ') or value.endswith(' '):
        return u'"' + value.replace('"', '""') + u'"'
    return value


def _write_csv(path, rows):
    with codecs.open(path, 'w', 'utf-8-sig') as fp:
        for row in rows:
            fp.write(u','.join([_csv_escape(x) for x in row]) + u'\r\n')


def _safe_filename(text):
    text = _u(text)
    text = re.sub(r'[\\/:*?"<>|]+', '_', text)
    text = re.sub(r'\s+', ' ', text).strip().rstrip('.')
    return text or 'Export'


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = '{0}_{1:02d}{2}'.format(base, index, ext)
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _doc(revit_ctx):
    try:
        return revit_ctx.doc
    except:
        return None


def _uidoc(revit_ctx):
    try:
        return revit_ctx.uidoc
    except:
        return None


def _app(revit_ctx):
    try:
        return revit_ctx.app
    except:
        try:
            return revit_ctx.doc.Application
        except:
            return None


def _show_message(message, title='Emperor BIM Toolkit', error=False):
    try:
        import emperor_ui
        emperor_ui.alert(_u(message), title, warn=error)
    except:
        _log(message)


def _element_name(elem):
    try:
        return _u(elem.Name)
    except:
        try:
            return _u(elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString())
        except:
            return u''


def _id_value(eid):
    # ElementId.IntegerValue is removed in newer Revit versions; Value exists from 2024.
    try:
        return int(eid.Value)
    except:
        try:
            return int(eid.IntegerValue)
        except:
            return -1


def _element_id(elem):
    try:
        return _id_value(elem.Id)
    except:
        return -1


def _safe_param(param):
    try:
        return param is not None and param.Definition is not None and (not param.IsReadOnly)
    except:
        return False


def _get_sheet_titleblock_name(doc, sheet):
    try:
        blocks = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_TitleBlocks).WhereElementIsNotElementType()
        for block in blocks:
            if block.OwnerViewId == sheet.Id:
                return _element_name(doc.GetElement(block.GetTypeId()))
    except:
        pass
    return ''


# -----------------------------------------------------------------------------
# SHARED PARAMETER-VALUE HELPERS (used by Sheet Builder and Bulk Edit)
# -----------------------------------------------------------------------------


def _param_to_text(param):
    if param is None:
        return ''
    try:
        st = param.StorageType
        if st == StorageType.String:
            return _u(param.AsString())
        if st == StorageType.Integer:
            try:
                vs = param.AsValueString()
                if vs:
                    return _u(vs)
            except:
                pass
            return _u(param.AsInteger())
        if st == StorageType.Double:
            try:
                vs = param.AsValueString()
                if vs is not None:
                    return _u(vs)
            except:
                pass
            return _u(param.AsDouble())
        if st == StorageType.ElementId:
            eid = param.AsElementId()
            try:
                if eid is not None and _id_value(eid) > 0:
                    target = param.Element.Document.GetElement(eid)
                    if target is not None:
                        return _u(_element_name(target))
            except:
                pass
            return _u(_id_value(eid))
    except:
        pass
    return ''


def _typed_value_from_input(param, raw):
    raw = _u(raw).strip()
    if param.StorageType == StorageType.String:
        return raw
    if param.StorageType == StorageType.Integer:
        lower = raw.lower()
        if lower in ['yes', 'true', 'on', '1']:
            return 1
        if lower in ['no', 'false', 'off', '0']:
            return 0
        return int(raw)
    if param.StorageType == StorageType.Double:
        value = float(raw.replace(',', '.'))
        try:
            unit_id = param.GetUnitTypeId()
            if unit_id is not None and not unit_id.Empty():
                value = UnitUtils.ConvertToInternalUnits(value, unit_id)
        except:
            pass
        return value
    if param.StorageType == StorageType.ElementId:
        return ElementId(int(raw))
    raise Exception('Unsupported parameter storage type.')


def _raw_param_value(param):
    if param.StorageType == StorageType.String:
        return param.AsString() or ''
    if param.StorageType == StorageType.Integer:
        return param.AsInteger()
    if param.StorageType == StorageType.Double:
        return param.AsDouble()
    if param.StorageType == StorageType.ElementId:
        return param.AsElementId()
    return None


def _values_equal(a, b):
    try:
        if isinstance(a, ElementId) and isinstance(b, ElementId):
            return _id_value(a) == _id_value(b)
        if isinstance(a, float) or isinstance(b, float):
            return abs(float(a) - float(b)) < 1e-9
    except:
        pass
    return a == b


def _set_param_value(param, value):
    if param.StorageType == StorageType.String:
        result = param.Set(_u(value))
    elif param.StorageType == StorageType.Integer:
        result = param.Set(int(value))
    elif param.StorageType == StorageType.Double:
        result = param.Set(float(value))
    elif param.StorageType == StorageType.ElementId:
        result = param.Set(value)
    else:
        raise Exception('Unsupported parameter storage type.')
    if result is False:
        raise Exception('Revit rejected the parameter value.')
    return result


def _format_new_value(doc, param, value):
    # Show the preview value the way Revit would display it (units, Yes/No).
    try:
        if param.StorageType == StorageType.Double:
            return _u(UnitFormatUtils.Format(doc.GetUnits(), param.Definition.GetDataType(), value, False))
        if param.StorageType == StorageType.ElementId:
            target = doc.GetElement(value)
            if target is not None:
                return _u(_element_name(target))
    except:
        pass
    return _u(value)




# -----------------------------------------------------------------------------
# WIDGET HELPERS FOR THE DiRoots-STYLE WINDOWS
# -----------------------------------------------------------------------------


def _checkbox(text, checked=False, callback=None, width=None):
    c = CheckBox()
    c.Content = _u(text)
    c.IsChecked = bool(checked)
    c.Margin = Thickness(6, 6, 8, 3)
    c.FontFamily = FontFamily('Segoe UI')
    c.FontSize = 12
    c.Foreground = _brush(INK)
    if width is not None:
        c.Width = width
    if callback:
        c.Click += _safe_handler(callback)
    return c


def _radio(text, group, checked=False, callback=None):
    r = RadioButton()
    r.Content = _u(text)
    r.GroupName = group
    r.IsChecked = bool(checked)
    r.Margin = Thickness(6, 6, 8, 3)
    r.FontFamily = FontFamily('Segoe UI')
    r.FontSize = 12
    r.Foreground = _brush(INK)
    if callback:
        r.Click += _safe_handler(callback)
    return r


def _menu_button(label, icon, items, primary=False):
    """A button that opens a drop-down menu. items = [(label, callback), ...]; None = separator."""
    holder = {}

    def show():
        menu = ContextMenu()
        for entry in items:
            if entry is None:
                menu.Items.Add(Separator())
                continue
            mi = MenuItem()
            mi.Header = _u(entry[0])
            mi.Click += _safe_handler(entry[1])
            menu.Items.Add(mi)
        menu.PlacementTarget = holder['button']
        menu.Placement = System.Windows.Controls.Primitives.PlacementMode.Bottom
        menu.IsOpen = True
    b = _button(label + u'  \u25BE', icon, show, primary)
    holder['button'] = b
    return b


def _row(*children):
    p = WrapPanel()
    p.Orientation = Orientation.Horizontal
    for c in children:
        p.Children.Add(c)
    return p


def _tabs():
    t = TabControl()
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = 12
    t.Margin = Thickness(0)
    t.BorderBrush = _brush(BORDER)
    t.BorderThickness = Thickness(0, 1, 0, 0)
    t.Background = _brush(WHITE)
    return t


def _add_tab(tabs, header, element):
    ti = TabItem()
    ti.Header = _u(header)
    ti.Content = element
    tabs.Items.Add(ti)
    return ti


def _doevents(win):
    # Let WPF repaint during a long loop (progress bars, status text).
    try:
        win.Dispatcher.Invoke(System.Action(lambda: None), System.Windows.Threading.DispatcherPriority.Background)
    except:
        pass


def _expand_path(text):
    """Replace %VARIABLE% environment variables first, then strftime codes (%Y %m %d %H %M %S).
    Order matters: strftime would read %UserName% as the week-number code %U."""
    text = _u(text)

    def env(m):
        name = m.group(1)
        for key in (name, name.upper()):
            if key in os.environ:
                return _u(os.environ[key])
        return m.group(0)
    text = re.sub(r'%([A-Za-z_][A-Za-z0-9_]*)%', env, text)
    # protect values that came from the environment from strftime: only format codes that are still raw
    try:
        text = time.strftime(text)
    except:
        pass
    return text


def _enum_value(enum_type, name):
    try:
        return getattr(enum_type, name)
    except:
        return None


def _ask_yes_no(message, title='Emperor BIM Toolkit'):
    try:
        import emperor_ui
        return emperor_ui.alert(_u(message), title, yes=True, no=True)
    except Exception:
        return MessageBox.Show(_u(message), title, MessageBoxButton.YesNo, MessageBoxImage.Question) == System.Windows.MessageBoxResult.Yes


def _input_dialog(owner, title, prompt, default=''):
    """Small modal text prompt. Returns the text or None."""
    win = Window()
    win.Title = _u(title)
    win.Width = 420
    win.SizeToContent = System.Windows.SizeToContent.Height
    win.WindowStartupLocation = WindowStartupLocation.CenterOwner
    win.ResizeMode = ResizeMode.NoResize
    win.Background = _brush('#F8F8F8')
    _glow(win)
    try:
        win.Owner = owner
    except:
        pass
    sp = StackPanel()
    sp.Margin = Thickness(14)
    sp.Children.Add(_text(prompt, 12, INK, False, True))
    box = _textbox(default, 380)
    sp.Children.Add(box)
    result = {'value': None}
    btns = StackPanel()
    btns.Orientation = Orientation.Horizontal
    btns.HorizontalAlignment = HorizontalAlignment.Right

    def ok():
        result['value'] = _u(box.Text)
        win.Close()
    btns.Children.Add(_button('OK', None, ok, True, 70))
    btns.Children.Add(_button('Cancel', None, lambda: win.Close(), False, 70))
    sp.Children.Add(btns)
    win.Content = sp
    win.ShowDialog()
    return result['value']


def _list_dialog(owner, title, prompt, items, multi=True, preselected=None, width=520, height=560):
    """Modal checklist / list picker. items: list of strings. Returns list of chosen strings or None."""
    win = Window()
    win.Title = _u(title)
    win.Width = width
    win.Height = height
    win.WindowStartupLocation = WindowStartupLocation.CenterOwner
    win.Background = _brush('#F8F8F8')
    _glow(win)
    try:
        win.Owner = owner
    except:
        pass
    root = DockPanel()
    top = StackPanel()
    top.Margin = Thickness(10, 10, 10, 4)
    top.Children.Add(_text(prompt, 12, INK, False, True))
    filter_box = _textbox('', None)
    top.Children.Add(filter_box)
    DockPanel.SetDock(top, System.Windows.Controls.Dock.Top)
    root.Children.Add(top)
    btns = StackPanel()
    btns.Orientation = Orientation.Horizontal
    btns.HorizontalAlignment = HorizontalAlignment.Right
    btns.Margin = Thickness(8)
    DockPanel.SetDock(btns, System.Windows.Controls.Dock.Bottom)
    root.Children.Add(btns)
    lb = ListBox()
    lb.SelectionMode = SelectionMode.Extended if multi else SelectionMode.Single
    lb.Margin = Thickness(10, 4, 10, 4)
    root.Children.Add(lb)
    picked = set([_u(x) for x in (preselected or [])])
    busy = {'v': False}

    def fill():
        busy['v'] = True
        try:
            lb.Items.Clear()
            needle = _u(filter_box.Text).strip().lower()
            for it in items:
                if not needle or needle in _u(it).lower():
                    lb.Items.Add(_u(it))
            for it in lb.Items:
                if _u(it) in picked:
                    lb.SelectedItems.Add(it)
        finally:
            busy['v'] = False

    def changed():
        if busy['v']:
            return
        visible = set([_u(x) for x in lb.Items])
        chosen = set([_u(x) for x in lb.SelectedItems])
        for n in visible:
            if n in chosen:
                picked.add(n)
            else:
                picked.discard(n)
    lb.SelectionChanged += _safe_handler(changed)
    filter_box.TextChanged += _safe_handler(fill)
    fill()
    result = {'value': None}

    def ok():
        result['value'] = [x for x in items if _u(x) in picked]
        win.Close()
    btns.Children.Add(_button('OK', None, ok, True, 70))
    btns.Children.Add(_button('Cancel', None, lambda: win.Close(), False, 70))
    win.Content = root
    win.ShowDialog()
    return result['value']


def _selected_rows(grid):
    rows = []
    try:
        for item in grid.SelectedItems:
            rows.append(item)
    except:
        pass
    return rows


def _profiles_dir(tool):
    path = os.path.join(APPDATA_DIR, tool)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except:
            pass
    return path


def _load_json(path, default=None):
    try:
        with codecs.open(path, 'r', 'utf-8-sig') as fp:
            return json.load(fp)
    except:
        return default


def _save_json(path, data):
    with codecs.open(path, 'w', 'utf-8') as fp:
        fp.write(json.dumps(data, indent=2))


def _view_type_label(view):
    try:
        return _u(view.ViewType)
    except:
        return ''


def _all_revisions(doc):
    result = []
    try:
        for rid in Revision.GetAllRevisionIds(doc):
            rev = doc.GetElement(rid)
            if rev is not None:
                result.append(rev)
    except:
        pass
    return result


def _revision_label(rev):
    try:
        return u'{0} - {1}'.format(_u(rev.RevisionNumber), _u(rev.Description))
    except:
        return _u(getattr(rev, 'Description', ''))


def _increment_text(text):
    """M-101 -> M-102, A9 -> A10, abc -> abc1."""
    text = _u(text)
    m = re.search(r'(\d+)(\D*)$', text)
    if not m:
        return text + u'1'
    digits = m.group(1)
    nxt = str(int(digits) + 1).zfill(len(digits))
    return text[:m.start(1)] + nxt + m.group(2)


def _enable_multi_check(grid, column='Export', after=None):
    """Ctrl/Shift multi-row highlight + Space / context menu to tick or untick every highlighted row."""
    try:
        grid.SelectionMode = System.Windows.Controls.DataGridSelectionMode.Extended
        grid.SelectionUnit = System.Windows.Controls.DataGridSelectionUnit.FullRow
    except:
        pass

    def toggle(value=None):
        rows = _selected_rows(grid)
        if not rows:
            return
        if value is None:
            value = not all([bool(r[column]) for r in rows])
        for r in rows:
            r[column] = bool(value)
        if after:
            after()

    def on_key(sender, args):
        try:
            if args.Key == System.Windows.Input.Key.Space:
                toggle()
                args.Handled = True
        except Exception as ex:
            _log('multi check key: {0}'.format(ex))
    grid.PreviewKeyDown += on_key
    menu = ContextMenu()
    for label, val in (('Check highlighted rows', True), ('Uncheck highlighted rows', False)):
        mi = MenuItem()
        mi.Header = label
        mi.Click += _safe_handler((lambda v: (lambda: toggle(v)))(val))
        menu.Items.Add(mi)
    grid.ContextMenu = menu
    return toggle


__all__ = [n for n in dir() if not n.startswith('__')]
