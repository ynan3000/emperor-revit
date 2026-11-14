# -*- coding: ascii -*-
"""Emperor - one red & white look for every Emperor window.

Used by every tool of the Emperor extension:
  - resources_xaml()  : brushes + styles to paste inside <Window.Resources> of a XAML window
                        (keys: Red, RedDark, RedTint, RedLine, Ink, Muted, HeaderBrush,
                         RedBtn, OutlineBtn, RedCheck, RedRadio + implicit styles for plain
                         Button / CheckBox / RadioButton / TextBox / ListBoxItem / ComboBoxItem)
  - inject(xaml_text) : replaces the marker <!--EMPEROR_THEME--> with resources_xaml()
  - dictionary()      : the same resources as a ResourceDictionary (for code-built windows)
  - enable_mouse_glow(window) : buttons light up where the mouse is (a soft glow that follows
                        the cursor), on top of the hover / press animation of the templates.
  - glow_layer()      : the XAML of the glow layer, used by the Exporter / Room & Space themes.

Everything is wrapped in try/except: if styling cannot load, the windows still open with
plain controls.
Author: Yahya Morcy
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

# ---------------------------------------------------------------- palette (Emperor)
RED = '#8B111C'        # main red
RED2 = '#B32330'       # bright red (hover border, focus, accents)
RED_DEEP = '#6E0C16'   # header gradient start
INK = '#303034'        # text
GRAY = '#77777D'       # secondary text
LIGHT = '#F7EFF0'      # light red tint
WHITE = '#FFFFFF'
BORDER = '#D8CBCD'     # neutral border
REDLINE = '#E2B3B8'    # red separator line
HOVER_BG = '#F7EBEC'   # hover fill of white buttons
PRESS_BG = '#E8CDD1'   # pressed fill of white buttons
SELECT = '#F3DADD'     # selected row
HOVERROW = '#FAF1F2'   # hovered row
WINDOW_BG = '#F8F8F8'
STATUS_BG = '#F3E9EA'
GREEN = '#327D50'

GLOW_NAME = 'EmperorGlow'
GLOW_ON_WHITE = '#33B32330'   # glow colour on white buttons (aRGB)
GLOW_ON_RED = '#55FFFFFF'     # glow colour on red buttons

NS = ('xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
      'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"')


def glow_layer(tag_color, radius=5):
    """XAML of the mouse-following glow layer for a Button template (name EmperorGlow)."""
    return (u'<Border x:Name="EmperorGlow" CornerRadius="' + str(radius) + u'" Opacity="0" '
            u'IsHitTestVisible="False" Tag="' + tag_color + u'"/>')


def glow_triggers():
    """Storyboards that fade the glow in / out with IsMouseOver (insert into a trigger)."""
    enter = (u'<DoubleAnimation Storyboard.TargetName="EmperorGlow" '
             u'Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.15"/>')
    leave = (u'<DoubleAnimation Storyboard.TargetName="EmperorGlow" '
             u'Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.25"/>')
    return enter, leave


def _button_style(key, primary):
    enter, leave = glow_triggers()
    if primary:
        bg, fg, bd, hover_bg, press_bg, hover_bd = RED, WHITE, RED, '#26FFFFFF', '#33000000', RED_DEEP
        glow = glow_layer(GLOW_ON_RED)
    else:
        bg, fg, bd, hover_bg, press_bg, hover_bd = WHITE, RED, BORDER, HOVER_BG, PRESS_BG, RED2
        glow = glow_layer(GLOW_ON_WHITE)
    return u'''
<Style x:Key="''' + key + u'''" TargetType="Button">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Background" Value="''' + bg + u'''"/>
  <Setter Property="Foreground" Value="''' + fg + u'''"/>
  <Setter Property="BorderBrush" Value="''' + bd + u'''"/>
  <Setter Property="BorderThickness" Value="1"/>
  <Setter Property="FontWeight" Value="SemiBold"/>
  <Setter Property="Padding" Value="14,6"/>
  <Setter Property="Margin" Value="0,3,8,3"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="Button">
        <Grid x:Name="root" RenderTransformOrigin="0.5,0.5">
          <Grid.RenderTransform><ScaleTransform x:Name="sc" ScaleX="1" ScaleY="1"/></Grid.RenderTransform>
          <Border x:Name="bd" CornerRadius="5" Background="{TemplateBinding Background}"
                  BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}"/>
          <Border x:Name="hv" CornerRadius="5" Background="''' + hover_bg + u'''" BorderBrush="''' + hover_bd + u'''"
                  BorderThickness="1" Opacity="0" IsHitTestVisible="False"/>
          ''' + glow + u'''
          <Border x:Name="pr" CornerRadius="5" Background="''' + press_bg + u'''" Opacity="0" IsHitTestVisible="False"/>
          <ContentPresenter Margin="{TemplateBinding Padding}" HorizontalAlignment="Center"
                            VerticalAlignment="Center" RecognizesAccessKey="True"/>
        </Grid>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Trigger.EnterActions><BeginStoryboard><Storyboard>
              <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.12"/>
              ''' + enter + u'''
            </Storyboard></BeginStoryboard></Trigger.EnterActions>
            <Trigger.ExitActions><BeginStoryboard><Storyboard>
              <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.18"/>
              ''' + leave + u'''
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
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED2 + u'''"/>
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
'''


def extras_xaml():
    """Implicit styles for the controls the first theme left plain: drop-down lists, right-click
    menus, expandable sections, tooltips. Safe to merge into ANY window (no keyed styles, no
    Button / CheckBox / TextBox styles), so the Exporter and Room & Space windows use it too."""
    return u'''
<Style x:Key="EkComboToggle" TargetType="ToggleButton">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="Focusable" Value="False"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ToggleButton">
        <Border x:Name="bd" CornerRadius="4" Background="{TemplateBinding Background}"
                BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="1">
          <Grid>
            <Border x:Name="hv" CornerRadius="4" Background="''' + HOVER_BG + u'''" Opacity="0"/>
            <Border x:Name="EmperorGlow" CornerRadius="4" Opacity="0" IsHitTestVisible="False" Tag="''' + GLOW_ON_WHITE + u'''"/>
            <Path x:Name="arrow" HorizontalAlignment="Right" VerticalAlignment="Center" Margin="0,0,9,0"
                  Data="M0,0 L4,4 L8,0" Stroke="''' + RED + u'''" StrokeThickness="1.7"
                  StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round"/>
          </Grid>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED2 + u'''"/>
            <Trigger.EnterActions><BeginStoryboard><Storyboard>
              <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.12"/>
              <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.15"/>
            </Storyboard></BeginStoryboard></Trigger.EnterActions>
            <Trigger.ExitActions><BeginStoryboard><Storyboard>
              <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.18"/>
              <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.25"/>
            </Storyboard></BeginStoryboard></Trigger.ExitActions>
          </Trigger>
          <Trigger Property="IsChecked" Value="True">
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED + u'''"/>
            <Setter TargetName="arrow" Property="Data" Value="M0,4 L4,0 L8,4"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="ComboBox">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Background" Value="White"/>
  <Setter Property="BorderBrush" Value="''' + BORDER + u'''"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="MinHeight" Value="24"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="ScrollViewer.HorizontalScrollBarVisibility" Value="Auto"/>
  <Setter Property="ScrollViewer.VerticalScrollBarVisibility" Value="Auto"/>
  <Setter Property="ScrollViewer.CanContentScroll" Value="True"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ComboBox">
        <Grid x:Name="root">
          <ToggleButton x:Name="tb" Style="{StaticResource EkComboToggle}" ClickMode="Press"
                        Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}"
                        IsChecked="{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}"/>
          <ContentPresenter x:Name="cp" IsHitTestVisible="False" Margin="8,2,26,2"
                            Content="{TemplateBinding SelectionBoxItem}"
                            ContentTemplate="{TemplateBinding SelectionBoxItemTemplate}"
                            ContentTemplateSelector="{TemplateBinding ItemTemplateSelector}"
                            VerticalAlignment="Center" HorizontalAlignment="Left"/>
          <TextBox x:Name="PART_EditableTextBox" Style="{x:Null}" Visibility="Hidden" Margin="6,2,26,2"
                   Background="Transparent" BorderThickness="0" VerticalAlignment="Center"
                   Foreground="{TemplateBinding Foreground}" IsReadOnly="{TemplateBinding IsReadOnly}"/>
          <Popup x:Name="PART_Popup" Placement="Bottom" IsOpen="{TemplateBinding IsDropDownOpen}"
                 AllowsTransparency="True" Focusable="False" PopupAnimation="Slide">
            <Border x:Name="dd" Background="White" BorderBrush="''' + RED2 + u'''" BorderThickness="1"
                    CornerRadius="4" Margin="0,2,0,0" SnapsToDevicePixels="True"
                    MinWidth="{Binding ActualWidth, ElementName=root}" MaxHeight="{TemplateBinding MaxDropDownHeight}">
              <ScrollViewer Margin="2" SnapsToDevicePixels="True">
                <StackPanel IsItemsHost="True" KeyboardNavigation.DirectionalNavigation="Contained"/>
              </ScrollViewer>
            </Border>
          </Popup>
        </Grid>
        <ControlTemplate.Triggers>
          <Trigger Property="HasItems" Value="False">
            <Setter TargetName="dd" Property="MinHeight" Value="30"/>
          </Trigger>
          <Trigger Property="IsEditable" Value="True">
            <Setter TargetName="PART_EditableTextBox" Property="Visibility" Value="Visible"/>
            <Setter TargetName="cp" Property="Visibility" Value="Hidden"/>
          </Trigger>
          <Trigger Property="IsEnabled" Value="False">
            <Setter TargetName="root" Property="Opacity" Value="0.5"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="ComboBoxItem">
  <Setter Property="Padding" Value="8,4"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ComboBoxItem">
        <Border x:Name="bd" Background="Transparent" Padding="{TemplateBinding Padding}">
          <ContentPresenter/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsHighlighted" Value="True">
            <Setter TargetName="bd" Property="Background" Value="''' + SELECT + u'''"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Foreground" Value="''' + RED + u'''"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="ToolTip">
  <Setter Property="Background" Value="White"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="BorderBrush" Value="''' + RED2 + u'''"/>
  <Setter Property="BorderThickness" Value="1"/>
  <Setter Property="Padding" Value="8,5"/>
</Style>

<Style TargetType="TabItem">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="TabItem">
        <Border x:Name="bd" Background="Transparent" BorderBrush="Transparent" BorderThickness="0,0,0,3"
                Padding="16,6,16,5" Margin="0,0,2,0">
          <ContentPresenter x:Name="cp" ContentSource="Header" TextElement.Foreground="''' + GRAY + u'''"
                            HorizontalAlignment="Center"/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="bd" Property="Background" Value="''' + LIGHT + u'''"/>
            <Setter TargetName="cp" Property="TextElement.Foreground" Value="''' + RED + u'''"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED + u'''"/>
            <Setter TargetName="bd" Property="Background" Value="White"/>
            <Setter TargetName="cp" Property="TextElement.Foreground" Value="''' + RED + u'''"/>
            <Setter TargetName="cp" Property="TextElement.FontWeight" Value="Bold"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="DataGridColumnHeader">
  <Setter Property="Background" Value="''' + LIGHT + u'''"/>
  <Setter Property="Foreground" Value="''' + RED + u'''"/>
  <Setter Property="FontWeight" Value="SemiBold"/>
  <Setter Property="Padding" Value="7,4,7,4"/>
  <Setter Property="BorderBrush" Value="''' + BORDER + u'''"/>
  <Setter Property="BorderThickness" Value="0,0,1,2"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Style.Triggers>
    <Trigger Property="IsMouseOver" Value="True">
      <Setter Property="Background" Value="''' + SELECT + u'''"/>
    </Trigger>
  </Style.Triggers>
</Style>

<Style TargetType="DataGridCell">
  <Setter Property="BorderThickness" Value="0"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Style.Triggers>
    <DataTrigger Binding="{Binding RelativeSource={RelativeSource AncestorType=DataGridRow}, Path=IsMouseOver}" Value="True">
      <Setter Property="Background" Value="''' + HOVERROW + u'''"/>
    </DataTrigger>
    <Trigger Property="IsSelected" Value="True">
      <Setter Property="Background" Value="''' + SELECT + u'''"/>
      <Setter Property="Foreground" Value="''' + INK + u'''"/>
      <Setter Property="BorderBrush" Value="Transparent"/>
    </Trigger>
  </Style.Triggers>
</Style>

<Style TargetType="ContextMenu">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ContextMenu">
        <Border Background="White" BorderBrush="''' + RED2 + u'''" BorderThickness="1" CornerRadius="5" Padding="3">
          <StackPanel IsItemsHost="True" KeyboardNavigation.DirectionalNavigation="Cycle"/>
        </Border>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="MenuItem">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="MenuItem">
        <Border x:Name="bd" Background="Transparent" CornerRadius="3" Padding="12,6,16,6"
                BorderThickness="3,0,0,0" BorderBrush="Transparent">
          <ContentPresenter ContentSource="Header" RecognizesAccessKey="True"/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsHighlighted" Value="True">
            <Setter TargetName="bd" Property="Background" Value="''' + SELECT + u'''"/>
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED + u'''"/>
            <Setter Property="Foreground" Value="''' + RED + u'''"/>
          </Trigger>
          <Trigger Property="IsEnabled" Value="False">
            <Setter TargetName="bd" Property="Opacity" Value="0.45"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="Separator">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="Separator">
        <Border Height="1" Margin="6,3" Background="''' + REDLINE + u'''"/>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

<Style TargetType="Expander">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="Expander">
        <DockPanel>
          <ToggleButton x:Name="hd" DockPanel.Dock="Top" Cursor="Hand" OverridesDefaultStyle="True"
                        IsChecked="{Binding IsExpanded, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}">
            <ToggleButton.Template>
              <ControlTemplate TargetType="ToggleButton">
                <Border x:Name="bd" Background="Transparent" CornerRadius="4" Padding="6,5"
                        BorderThickness="0,0,0,1" BorderBrush="''' + REDLINE + u'''">
                  <StackPanel Orientation="Horizontal">
                    <Path x:Name="arrow" Data="M0,0 L4,4 L0,8" Stroke="''' + RED + u'''" StrokeThickness="1.8"
                          VerticalAlignment="Center" Margin="2,0,10,0"
                          StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round"/>
                    <ContentPresenter VerticalAlignment="Center"/>
                  </StackPanel>
                </Border>
                <ControlTemplate.Triggers>
                  <Trigger Property="IsMouseOver" Value="True">
                    <Setter TargetName="bd" Property="Background" Value="''' + HOVER_BG + u'''"/>
                    <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED2 + u'''"/>
                  </Trigger>
                  <Trigger Property="IsChecked" Value="True">
                    <Setter TargetName="arrow" Property="Data" Value="M0,0 L4,4 L8,0"/>
                  </Trigger>
                </ControlTemplate.Triggers>
              </ControlTemplate>
            </ToggleButton.Template>
            <ContentPresenter Content="{TemplateBinding Header}" TextElement.Foreground="''' + RED + u'''"/>
          </ToggleButton>
          <ContentPresenter x:Name="body" Margin="{TemplateBinding Padding}" Visibility="Collapsed"/>
        </DockPanel>
        <ControlTemplate.Triggers>
          <Trigger Property="IsExpanded" Value="True">
            <Setter TargetName="body" Property="Visibility" Value="Visible"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
'''


def resources_xaml():
    """Brushes and styles, ready to paste inside <Window.Resources> ... </Window.Resources>."""
    return u'''
<SolidColorBrush x:Key="Red" Color="''' + RED + u'''"/>
<SolidColorBrush x:Key="RedDark" Color="''' + RED_DEEP + u'''"/>
<SolidColorBrush x:Key="RedBright" Color="''' + RED2 + u'''"/>
<SolidColorBrush x:Key="RedTint" Color="''' + LIGHT + u'''"/>
<SolidColorBrush x:Key="RedLine" Color="''' + REDLINE + u'''"/>
<SolidColorBrush x:Key="Line" Color="''' + BORDER + u'''"/>
<SolidColorBrush x:Key="Ink" Color="''' + INK + u'''"/>
<SolidColorBrush x:Key="Muted" Color="''' + GRAY + u'''"/>
<SolidColorBrush x:Key="WindowBg" Color="''' + WINDOW_BG + u'''"/>
<LinearGradientBrush x:Key="HeaderBrush" StartPoint="0,0" EndPoint="1,0">
  <GradientStop Color="''' + RED_DEEP + u'''" Offset="0"/>
  <GradientStop Color="''' + RED + u'''" Offset="0.55"/>
  <GradientStop Color="''' + RED2 + u'''" Offset="1"/>
</LinearGradientBrush>
''' + _button_style('RedBtn', True) + _button_style('OutlineBtn', False) + u'''
<Style TargetType="Button" BasedOn="{StaticResource OutlineBtn}"/>

<Style x:Key="RedCheck" TargetType="CheckBox">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="CheckBox">
        <StackPanel x:Name="root" Orientation="Horizontal" Background="Transparent">
          <Grid Width="17" Height="17" VerticalAlignment="Center">
            <Border x:Name="box" CornerRadius="4" BorderThickness="1.5" BorderBrush="''' + GRAY + u'''" Background="White"/>
            <Path x:Name="tick" Data="M4,8.8 L7,11.8 L13,5" Stroke="White" StrokeThickness="2"
                  StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Visibility="Collapsed"/>
          </Grid>
          <ContentPresenter Margin="7,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
        </StackPanel>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="box" Property="BorderBrush" Value="''' + RED2 + u'''"/>
            <Setter TargetName="box" Property="Background" Value="''' + LIGHT + u'''"/>
          </Trigger>
          <Trigger Property="IsChecked" Value="True">
            <Setter TargetName="box" Property="Background" Value="''' + RED + u'''"/>
            <Setter TargetName="box" Property="BorderBrush" Value="''' + RED + u'''"/>
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
<Style TargetType="CheckBox" BasedOn="{StaticResource RedCheck}"/>

<Style x:Key="RedRadio" TargetType="RadioButton">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="Margin" Value="0,4,0,4"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="RadioButton">
        <StackPanel x:Name="root" Orientation="Horizontal" Background="Transparent">
          <Grid Width="17" Height="17" VerticalAlignment="Center">
            <Ellipse x:Name="ring" Stroke="''' + GRAY + u'''" StrokeThickness="1.5" Fill="White"/>
            <Ellipse x:Name="dot" Width="8" Height="8" Fill="''' + RED + u'''" Visibility="Collapsed"/>
          </Grid>
          <ContentPresenter Margin="7,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
        </StackPanel>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="ring" Property="Stroke" Value="''' + RED2 + u'''"/>
            <Setter TargetName="ring" Property="Fill" Value="''' + LIGHT + u'''"/>
          </Trigger>
          <Trigger Property="IsChecked" Value="True">
            <Setter TargetName="ring" Property="Stroke" Value="''' + RED + u'''"/>
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
<Style TargetType="RadioButton" BasedOn="{StaticResource RedRadio}"/>

<Style x:Key="EkTextBox" TargetType="TextBox">
  <Setter Property="OverridesDefaultStyle" Value="True"/>
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="Background" Value="White"/>
  <Setter Property="BorderBrush" Value="''' + BORDER + u'''"/>
  <Setter Property="BorderThickness" Value="1"/>
  <Setter Property="Foreground" Value="''' + INK + u'''"/>
  <Setter Property="Padding" Value="6,0"/>
  <Setter Property="MinHeight" Value="26"/>
  <Setter Property="VerticalContentAlignment" Value="Center"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="TextBox">
        <Border x:Name="bd" CornerRadius="4" Background="{TemplateBinding Background}"
                BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}">
          <ScrollViewer x:Name="PART_ContentHost" Margin="{TemplateBinding Padding}" VerticalAlignment="Center"/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED2 + u'''"/>
          </Trigger>
          <Trigger Property="IsKeyboardFocused" Value="True">
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED + u'''"/>
          </Trigger>
          <Trigger Property="IsEnabled" Value="False">
            <Setter TargetName="bd" Property="Opacity" Value="0.5"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
<Style TargetType="TextBox" BasedOn="{StaticResource EkTextBox}"/>

<Style TargetType="ListBoxItem">
  <Setter Property="SnapsToDevicePixels" Value="True"/>
  <Setter Property="Padding" Value="8,4"/>
  <Setter Property="Cursor" Value="Hand"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ListBoxItem">
        <Border x:Name="bd" Background="Transparent" BorderThickness="3,0,0,0" BorderBrush="Transparent"
                Padding="{TemplateBinding Padding}" Margin="1">
          <ContentPresenter/>
        </Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="bd" Property="Background" Value="''' + HOVERROW + u'''"/>
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + REDLINE + u'''"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter TargetName="bd" Property="Background" Value="''' + SELECT + u'''"/>
            <Setter TargetName="bd" Property="BorderBrush" Value="''' + RED + u'''"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>

''' + extras_xaml()


def inject(xaml_text):
    """Put the Emperor resources where the XAML has the marker <!--EMPEROR_THEME-->."""
    return xaml_text.replace(u'<!--EMPEROR_THEME-->', resources_xaml())


_CACHE = {}


def dictionary():
    """The Emperor resources as one ResourceDictionary (None if it cannot load)."""
    if 'dict' in _CACHE:
        return _CACHE['dict']
    result = None
    try:
        from System.IO import StringReader
        from System.Windows.Markup import XamlReader
        text = u'<ResourceDictionary ' + NS + u'>' + resources_xaml() + u'</ResourceDictionary>'
        result = XamlReader.Parse(text)
    except Exception:
        result = None
    _CACHE['dict'] = result
    return result


def extras_dictionary():
    """Only the extra implicit styles (drop-downs, menus, expanders, tooltips) as a dictionary."""
    if 'extras' in _CACHE:
        return _CACHE['extras']
    result = None
    try:
        from System.IO import StringReader
        from System.Windows.Markup import XamlReader
        text = u'<ResourceDictionary ' + NS + u'>' + extras_xaml() + u'</ResourceDictionary>'
        result = XamlReader.Parse(text)
    except Exception:
        result = None
    _CACHE['extras'] = result
    return result


def add_extras(window):
    """Give a window that has its own theme the Emperor drop-downs / menus / expanders."""
    try:
        d = extras_dictionary()
        if d is not None:
            window.Resources.MergedDictionaries.Add(d)
            return True
    except Exception:
        pass
    return False


def apply_theme(window):
    """Merge the Emperor resources into a code-built window. Returns True when done."""
    try:
        d = dictionary()
        if d is not None:
            window.Resources.MergedDictionaries.Add(d)
            return True
    except Exception:
        pass
    return False


def header_brush():
    try:
        from System.Windows.Media import LinearGradientBrush, GradientStop, Color
        from System.Windows import Point
        gb = LinearGradientBrush()
        gb.StartPoint = Point(0, 0)
        gb.EndPoint = Point(1, 0)
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x6E, 0x0C, 0x16), 0.0))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x8B, 0x11, 0x1C), 0.55))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0xB3, 0x23, 0x30), 1.0))
        return gb
    except Exception:
        return None


# ---------------------------------------------------------------- mouse-following glow
def _argb(hex_color):
    from System.Windows.Media import Color
    h = hex_color.replace('#', '')
    if len(h) == 6:
        h = 'FF' + h
    return Color.FromArgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))


def _find_button(source, window):
    """Walk up from the element under the mouse to the Button that contains it."""
    from System.Windows.Controls.Primitives import ButtonBase
    from System.Windows.Media import VisualTreeHelper, Visual
    from System.Windows import LogicalTreeHelper
    el = source
    steps = 0
    while el is not None and steps < 40:
        if isinstance(el, ButtonBase):
            return el
        if el is window:
            return None
        parent = None
        try:
            if isinstance(el, Visual):
                parent = VisualTreeHelper.GetParent(el)
        except Exception:
            parent = None
        if parent is None:
            try:
                parent = LogicalTreeHelper.GetParent(el)
            except Exception:
                parent = None
        el = parent
        steps += 1
    return None


def _update_glow(button, args):
    try:
        template = button.Template
        if template is None:
            return
        glow = template.FindName(GLOW_NAME, button)
        if glow is None:
            return
        w = button.ActualWidth
        h = button.ActualHeight
        if w <= 0 or h <= 0:
            return
        p = args.GetPosition(button)
        from System.Windows import Point
        from System.Windows.Media import RadialGradientBrush, GradientStop, Color
        brush = glow.Background
        if not isinstance(brush, RadialGradientBrush) or brush.IsFrozen:
            color = _argb(str(glow.Tag) if glow.Tag else GLOW_ON_WHITE)
            clear = Color.FromArgb(0, color.R, color.G, color.B)
            brush = RadialGradientBrush()
            brush.GradientStops.Add(GradientStop(color, 0.0))
            brush.GradientStops.Add(GradientStop(clear, 1.0))
            glow.Background = brush
        # radius: about 70 px around the cursor whatever the button size
        brush.RadiusX = min(2.0, 70.0 / w)
        brush.RadiusY = min(3.0, 70.0 / h)
        center = Point(p.X / w, p.Y / h)
        brush.Center = center
        brush.GradientOrigin = center
    except Exception:
        pass


def enable_mouse_glow(window):
    """Let every Emperor-styled button of the window follow the mouse with a soft glow."""
    try:
        from System.Windows import UIElement
        from System.Windows.Input import MouseEventHandler

        def on_move(sender, args):
            try:
                btn = _find_button(args.OriginalSource, window)
                if btn is not None:
                    _update_glow(btn, args)
            except Exception:
                pass

        window.AddHandler(UIElement.PreviewMouseMoveEvent, MouseEventHandler(on_move), True)
        return True
    except Exception:
        return False


def style_window(window):
    """apply_theme + enable_mouse_glow for code-built windows."""
    apply_theme(window)
    enable_mouse_glow(window)


# ---------------------------------------------------------------- Emperor message window
_ALERT_XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Emperor" Width="460" SizeToContent="Height" MaxHeight="640"
        WindowStartupLocation="CenterOwner" ResizeMode="NoResize" ShowInTaskbar="False"
        Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="18,10">
      <TextBlock x:Name="TitleText" Foreground="White" FontSize="15" FontWeight="Bold" TextWrapping="Wrap"/>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="#D8CBCD" BorderThickness="0,1,0,0" Padding="12,7">
      <DockPanel>
        <Button x:Name="CopyBtn" DockPanel.Dock="Left" Content="Copy" Style="{StaticResource OutlineBtn}" MinWidth="70"
                ToolTip="Copy this message"/>
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
          <Button x:Name="YesBtn" Content="OK" Style="{StaticResource RedBtn}" MinWidth="86" IsDefault="True"/>
          <Button x:Name="NoBtn" Content="No" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3"
                  IsCancel="True" Visibility="Collapsed"/>
        </StackPanel>
      </DockPanel>
    </Border>
    <Border Margin="10" Background="White" BorderBrush="#D8CBCD" BorderThickness="1" CornerRadius="6">
      <DockPanel>
        <Border x:Name="Mark" DockPanel.Dock="Left" Width="4" CornerRadius="2" Margin="0,8,0,8"
                Background="{StaticResource Red}"/>
        <ScrollViewer VerticalScrollBarVisibility="Auto" MaxHeight="420" Margin="10,10,10,10">
          <TextBox x:Name="Body" Style="{x:Null}" IsReadOnly="True" BorderThickness="0" Background="Transparent"
                   TextWrapping="Wrap" Foreground="#303034" FontSize="12.5"/>
        </ScrollViewer>
      </DockPanel>
    </Border>
  </DockPanel>
</Window>'''


def alert(message, title='Emperor', yes=False, no=False, owner=None, warn=False, **_ignored):
    """Emperor-style replacement for pyrevit forms.alert / MessageBox.
    OK only by default; yes=True, no=True gives Yes / No. Returns True for OK / Yes."""
    text = u'%s' % (message,)
    try:
        from System.Windows.Markup import XamlReader
        from System.Windows import Visibility, Clipboard
        win = XamlReader.Parse(inject(_ALERT_XAML))
        enable_mouse_glow(win)
        win.Title = u'%s' % title
        win.FindName('TitleText').Text = u'%s' % title
        win.FindName('Body').Text = text
        if warn:
            try:
                from System.Windows.Media import SolidColorBrush, Color
                win.FindName('Mark').Background = SolidColorBrush(Color.FromRgb(0xE6, 0x51, 0x00))
            except Exception:
                pass
        yes_btn, no_btn = win.FindName('YesBtn'), win.FindName('NoBtn')
        if yes or no:
            yes_btn.Content = 'Yes'
            no_btn.Visibility = Visibility.Visible
        state = {'value': False}

        def on_yes(sender, args):
            state['value'] = True
            win.Close()

        def on_no(sender, args):
            state['value'] = False
            win.Close()

        def on_copy(sender, args):
            try:
                Clipboard.SetText(text)
            except Exception:
                pass
        yes_btn.Click += on_yes
        no_btn.Click += on_no
        win.FindName('CopyBtn').Click += on_copy
        placed = False
        if owner is not None:
            try:
                win.Owner = owner
                placed = True
            except Exception:
                placed = False
        if not placed:
            try:
                from System.Windows.Interop import WindowInteropHelper
                from System.Diagnostics import Process
                WindowInteropHelper(win).Owner = Process.GetCurrentProcess().MainWindowHandle
            except Exception:
                pass
            from System.Windows import WindowStartupLocation
            win.WindowStartupLocation = WindowStartupLocation.CenterScreen
            win.Topmost = True      # never hide behind another open Emperor window
        win.ShowDialog()
        return state['value']
    except Exception:
        try:
            from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
            if yes or no:
                return MessageBox.Show(text, u'%s' % title, MessageBoxButton.YesNo) == MessageBoxResult.Yes
            MessageBox.Show(text, u'%s' % title)
            return True
        except Exception:
            return False


_CHOOSE_XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Emperor" Width="420" Height="420"
        WindowStartupLocation="CenterScreen" ResizeMode="CanResize" ShowInTaskbar="False" Topmost="True"
        Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="16,10">
      <TextBlock x:Name="TitleText" Foreground="White" FontSize="15" FontWeight="Bold" TextWrapping="Wrap"/>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="#D8CBCD" BorderThickness="0,1,0,0" Padding="12,7">
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="OkBtn" Content="OK" Style="{StaticResource RedBtn}" MinWidth="86" IsDefault="True"/>
        <Button x:Name="CancelBtn" Content="Cancel" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
      </StackPanel>
    </Border>
    <TextBlock x:Name="Prompt" DockPanel.Dock="Top" Margin="12,10,12,4" TextWrapping="Wrap" Foreground="#77777D"/>
    <Border Margin="10,4,10,10" Background="White" BorderBrush="#D8CBCD" BorderThickness="1" CornerRadius="6">
      <ListBox x:Name="Items" BorderThickness="0" SelectionMode="Extended"/>
    </Border>
  </DockPanel>
</Window>'''


def choose(title, items, prompt=u'Ctrl / Shift + click to pick several.', multi=True, select_all=True,
           preselect=None, owner=None):
    """Emperor list picker. Returns the list of chosen indexes (empty = cancelled).
    preselect: indexes to pre-select (overrides select_all). owner: WPF window to stay on top of."""
    from System.Windows.Markup import XamlReader
    from System.Windows.Controls import SelectionMode
    win = XamlReader.Parse(inject(_CHOOSE_XAML))
    enable_mouse_glow(win)
    win.Title = u'%s' % title
    win.FindName('TitleText').Text = u'%s' % title
    win.FindName('Prompt').Text = u'%s' % prompt
    lb = win.FindName('Items')
    if not multi:
        lb.SelectionMode = SelectionMode.Single
    for it in items:
        lb.Items.Add(u'%s' % it)
    if preselect is not None:
        for i in preselect:
            if 0 <= i < lb.Items.Count:
                lb.SelectedItems.Add(lb.Items[i])
    elif select_all and multi:
        lb.SelectAll()
    elif lb.Items.Count:
        lb.SelectedIndex = 0
    if owner is not None:
        try:
            win.Owner = owner
            win.Topmost = False
            from System.Windows import WindowStartupLocation
            win.WindowStartupLocation = WindowStartupLocation.CenterOwner
        except Exception:
            pass
    state = {'picked': []}

    def ok(sender, args):
        state['picked'] = sorted(lb.Items.IndexOf(x) for x in lb.SelectedItems)
        win.Close()

    def cancel(sender, args):
        state['picked'] = []
        win.Close()
    win.FindName('OkBtn').Click += ok
    win.FindName('CancelBtn').Click += cancel
    lb.MouseDoubleClick += ok
    win.ShowDialog()
    return state['picked']


_ASK_XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Emperor" Width="470" SizeToContent="Height"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize" ShowInTaskbar="False" Topmost="True"
        Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="16,10">
      <TextBlock x:Name="TitleText" Foreground="White" FontSize="15" FontWeight="Bold" TextWrapping="Wrap"/>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="#D8CBCD" BorderThickness="0,1,0,0" Padding="12,7">
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="OkBtn" Content="OK" Style="{StaticResource RedBtn}" MinWidth="86" IsDefault="True"/>
        <Button x:Name="CancelBtn" Content="Cancel" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
      </StackPanel>
    </Border>
    <StackPanel Margin="14,10,14,12">
      <TextBlock x:Name="Prompt" TextWrapping="Wrap" Foreground="#303034" Margin="0,0,0,8"/>
      <TextBox x:Name="Answer" Height="30" Padding="6,0" FontSize="13" VerticalContentAlignment="Center"/>
    </StackPanel>
  </DockPanel>
</Window>'''


def ask_text(title, prompt, default=u''):
    """Emperor text prompt. Returns the text, or None when cancelled."""
    from System.Windows.Markup import XamlReader
    win = XamlReader.Parse(inject(_ASK_XAML))
    enable_mouse_glow(win)
    win.Title = u'%s' % title
    win.FindName('TitleText').Text = u'%s' % title
    win.FindName('Prompt').Text = u'%s' % prompt
    box = win.FindName('Answer')
    box.Text = u'%s' % (default or u'')
    state = {'value': None}

    def ok(sender, args):
        state['value'] = u'%s' % box.Text
        win.Close()

    def cancel(sender, args):
        state['value'] = None
        win.Close()
    win.FindName('OkBtn').Click += ok
    win.FindName('CancelBtn').Click += cancel
    win.Loaded += lambda s, a: (box.Focus(), box.SelectAll())
    win.ShowDialog()
    return state['value']


def bring_to_front(hwnd):
    """Restore and activate a native window (e.g. Revit's main window) by its handle."""
    try:
        import ctypes
        h = hwnd.ToInt64() if hasattr(hwnd, 'ToInt64') else int(hwnd)
        if not h:
            return False
        u32 = ctypes.windll.user32
        hp = ctypes.c_void_p(h)
        if u32.IsIconic(hp):
            u32.ShowWindow(hp, 9)         # SW_RESTORE
        u32.SetForegroundWindow(hp)
        return True
    except Exception:
        return False


def keep_owner_in_front(window, hwnd):
    """A modeless tool window: when it closes, hand the focus back to Revit, so Windows does not
    bring another program to the front (Revit looked 'minimized')."""
    def closing(sender, args):
        try:
            if window.Owner is not None:
                window.Owner.Activate()
        except Exception:
            pass
        bring_to_front(hwnd)

    def closed(sender, args):
        bring_to_front(hwnd)
    try:
        window.Closing += closing
        window.Closed += closed
    except Exception:
        pass
