# -*- coding: utf-8 -*-
"""Red and white UI definitions (XAML) for the Link Manager (Emperor theme).

Kept ASCII-only on purpose. Any special glyphs are added from code.
"""

NS = ('xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
      'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"')

# Shared Emperor red & white resources (same look as every Emperor window).
from emperor_ui import resources_xaml as _emperor_resources
STYLES = _emperor_resources()

MAIN_XAML = u'''<Window @@NS@@
        Title="Link Manager" Height="780" Width="1180" MinHeight="520" MinWidth="860"
        WindowStartupLocation="CenterScreen" Background="White"
        FontFamily="Segoe UI" FontSize="13" ShowInTaskbar="False">
  <Window.Resources>
@@STYLES@@
  </Window.Resources>
  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <Border Grid.Row="0" Background="{StaticResource HeaderBrush}" Padding="20,12">
      <DockPanel>
        <TextBlock x:Name="SummaryText" DockPanel.Dock="Right" Foreground="White" FontSize="13"
                   VerticalAlignment="Center" HorizontalAlignment="Right"/>
        <StackPanel>
          <TextBlock Text="LINK MANAGER" Foreground="White" FontSize="22" FontWeight="Bold"/>
          <TextBlock Text="Revit links, instances, positions and worksets" Foreground="White"
                     Opacity="0.85" FontSize="12.5" Margin="0,2,0,0"/>
        </StackPanel>
      </DockPanel>
    </Border>

    <Border Grid.Row="1" Background="White" BorderBrush="{StaticResource RedLine}"
            BorderThickness="0,0,0,1" Padding="18,6">
      <StackPanel>
        <WrapPanel VerticalAlignment="Center">
          <CheckBox x:Name="SelectAll" Style="{StaticResource RedCheck}" Content="Select all shown"
                    Margin="0,0,22,0" VerticalAlignment="Center" FontWeight="SemiBold"/>
          <Button x:Name="BtnPinSel" Style="{StaticResource RedBtn}" Content="Pin selected"/>
          <Button x:Name="BtnUnpinSel" Style="{StaticResource OutlineBtn}" Content="Unpin selected"/>
          <Button x:Name="BtnPinAll" Style="{StaticResource RedBtn}" Content="Pin all"/>
          <Button x:Name="BtnUnpinAll" Style="{StaticResource OutlineBtn}" Content="Unpin all"/>
          <Border Width="1" Background="{StaticResource RedLine}" Margin="6,4,14,4"/>
          <Button x:Name="BtnLink" Style="{StaticResource RedBtn}" Content="Link files..."/>
          <Button x:Name="BtnCopy" Style="{StaticResource RedBtn}" Content="Copy to model..."/>
          <Button x:Name="BtnReloadAll" Style="{StaticResource RedBtn}" Content="Reload all"/>
          <Button x:Name="BtnReloadSel" Style="{StaticResource OutlineBtn}" Content="Reload selected"/>
          <Button x:Name="BtnRefresh" Style="{StaticResource OutlineBtn}" Content="Refresh table"/>
        </WrapPanel>
        <WrapPanel VerticalAlignment="Center">
          <TextBlock Text="SELECTED LINKS" Foreground="{StaticResource Muted}" FontSize="10.5"
                     FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,10,0"/>
          <Button x:Name="BtnUnload" Style="{StaticResource OutlineBtn}" Content="Unload"/>
          <Button x:Name="BtnRemove" Style="{StaticResource OutlineBtn}" Content="Remove"/>
          <Button x:Name="BtnOverlay" Style="{StaticResource OutlineBtn}" Content="Make Overlay"/>
          <Button x:Name="BtnAttachment" Style="{StaticResource OutlineBtn}" Content="Make Attachment"/>
          <Button x:Name="BtnRoomOn" Style="{StaticResource OutlineBtn}" Content="Room bounding ON"/>
          <Button x:Name="BtnRoomOff" Style="{StaticResource OutlineBtn}" Content="Room bounding OFF"/>
          <Button x:Name="BtnSelectRevit" Style="{StaticResource OutlineBtn}" Content="Select in Revit"/>
          <Border Width="1" Background="{StaticResource RedLine}" Margin="6,4,14,4"/>
          <Button x:Name="BtnExport" Style="{StaticResource OutlineBtn}" Content="Export CSV..."/>
          <Button x:Name="BtnExpand" Style="{StaticResource OutlineBtn}" Content="Expand all"/>
          <Button x:Name="BtnCollapse" Style="{StaticResource OutlineBtn}" Content="Collapse all"/>
        </WrapPanel>
        <WrapPanel VerticalAlignment="Center">
          <TextBlock Text="FILTER" Foreground="{StaticResource Muted}" FontSize="10.5"
                     FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,10,0"/>
          <TextBox x:Name="TxtSearch" Width="230" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,3,10,3"
                   BorderBrush="{StaticResource Red}" ToolTip="Search link, path, workset, site, level..."/>
          <ComboBox x:Name="CbSite" Width="210" Margin="0,3,12,3" ToolTip="Shared site"/>
          <CheckBox x:Name="ChkUnpinned" Style="{StaticResource RedCheck}" Content="Not fully pinned"
                    Margin="0,0,16,0" VerticalAlignment="Center"/>
          <CheckBox x:Name="ChkProblems" Style="{StaticResource RedCheck}" Content="Not loaded / not found"
                    Margin="0,0,14,0" VerticalAlignment="Center"/>
          <Button x:Name="BtnClearFilter" Style="{StaticResource OutlineBtn}" Content="Clear filters"/>
        </WrapPanel>
      </StackPanel>
    </Border>

    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto" Background="White">
      <StackPanel x:Name="LinksPanel" Margin="18,14,18,8" HorizontalAlignment="Left"/>
    </ScrollViewer>

    <Border Grid.Row="3" Background="{StaticResource RedTint}" BorderBrush="{StaticResource RedLine}"
            BorderThickness="0,1,0,0" Padding="18,9">
      <DockPanel>
        <Button x:Name="BtnClose" DockPanel.Dock="Right" Style="{StaticResource RedBtn}"
                Content="Close" Margin="12,0,0,0" Padding="22,6"/>
        <TextBlock x:Name="StatusText" VerticalAlignment="Center" Foreground="{StaticResource Ink}"
                   TextTrimming="CharacterEllipsis"/>
      </DockPanel>
    </Border>
  </Grid>
</Window>
'''

LINK_XAML = u'''<Window @@NS@@
        Title="Link Files" Height="760" Width="720" MinHeight="560" MinWidth="620"
        WindowStartupLocation="CenterOwner" Background="White"
        FontFamily="Segoe UI" FontSize="13" ShowInTaskbar="False">
  <Window.Resources>
@@STYLES@@
  </Window.Resources>
  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <Border Grid.Row="0" Background="{StaticResource HeaderBrush}" Padding="20,12">
      <StackPanel>
        <TextBlock Text="LINK MULTIPLE FILES" Foreground="White" FontSize="20" FontWeight="Bold"/>
        <TextBlock Text="Pick the models, choose how they are linked, and link them all in one go"
                   Foreground="White" Opacity="0.85" FontSize="12.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto">
      <StackPanel Margin="20,16,20,10">

        <TextBlock Text="1.  MODELS TO LINK" Foreground="{StaticResource Red}" FontWeight="Bold"/>
        <Border BorderBrush="{StaticResource RedLine}" BorderThickness="1" CornerRadius="6" Margin="0,6,0,0">
          <ListBox x:Name="FileList" Height="170" BorderThickness="0" SelectionMode="Extended"/>
        </Border>
        <WrapPanel Margin="0,8,0,0">
          <Button x:Name="BtnAdd" Style="{StaticResource RedBtn}" Content="Add files..."/>
          <Button x:Name="BtnRemove" Style="{StaticResource OutlineBtn}" Content="Remove selected"/>
          <Button x:Name="BtnClear" Style="{StaticResource OutlineBtn}" Content="Clear list"/>
        </WrapPanel>

        <TextBlock Text="2.  HOW TO LINK THEM" Foreground="{StaticResource Red}" FontWeight="Bold"
                   Margin="0,14,0,0"/>
        <Grid Margin="0,6,0,0">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="12"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>

          <StackPanel Grid.Column="0">
            <Border BorderBrush="{StaticResource RedLine}" BorderThickness="1" CornerRadius="6" Padding="12,8">
              <StackPanel>
                <TextBlock Text="PATH TYPE" Foreground="{StaticResource Muted}" FontSize="11" FontWeight="Bold"/>
                <RadioButton x:Name="RbRelative" GroupName="PathT" Style="{StaticResource RedRadio}"
                             Content="Relative" IsChecked="True"/>
                <RadioButton x:Name="RbAbsolute" GroupName="PathT" Style="{StaticResource RedRadio}"
                             Content="Absolute"/>
              </StackPanel>
            </Border>
            <Border BorderBrush="{StaticResource RedLine}" BorderThickness="1" CornerRadius="6"
                    Padding="12,8" Margin="0,12,0,0">
              <StackPanel>
                <TextBlock Text="REFERENCE TYPE" Foreground="{StaticResource Muted}" FontSize="11" FontWeight="Bold"/>
                <RadioButton x:Name="RbOverlay" GroupName="RefT" Style="{StaticResource RedRadio}"
                             Content="Overlay" IsChecked="True"/>
                <RadioButton x:Name="RbAttachment" GroupName="RefT" Style="{StaticResource RedRadio}"
                             Content="Attachment"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <StackPanel Grid.Column="2">
            <Border BorderBrush="{StaticResource RedLine}" BorderThickness="1" CornerRadius="6" Padding="12,8">
              <StackPanel>
                <TextBlock Text="POSITIONING" Foreground="{StaticResource Muted}" FontSize="11" FontWeight="Bold"/>
                <RadioButton x:Name="RbOrigin" GroupName="PosT" Style="{StaticResource RedRadio}"
                             Content="Origin to Origin" IsChecked="True"/>
                <RadioButton x:Name="RbShared" GroupName="PosT" Style="{StaticResource RedRadio}"
                             Content="Shared Coordinates"/>
              </StackPanel>
            </Border>
            <Border BorderBrush="{StaticResource RedLine}" BorderThickness="1" CornerRadius="6"
                    Padding="12,8" Margin="0,12,0,0">
              <StackPanel>
                <TextBlock Text="WORKSETS OF THE LINKED MODEL" Foreground="{StaticResource Muted}"
                           FontSize="11" FontWeight="Bold"/>
                <ComboBox x:Name="CbWorksets" Margin="0,6,0,0" SelectedIndex="0">
                  <ComboBoxItem Content="Open last viewed"/>
                  <ComboBoxItem Content="Open all worksets"/>
                  <ComboBoxItem Content="Close all worksets"/>
                </ComboBox>
              </StackPanel>
            </Border>
          </StackPanel>
        </Grid>

        <CheckBox x:Name="ChkPin" Style="{StaticResource RedCheck}" IsChecked="True"
                  Content="Pin the new link instances after linking" Margin="0,16,0,0"/>
        <CheckBox x:Name="ChkRoomBounding" Style="{StaticResource RedCheck}" IsChecked="False"
                  Content="Turn Room Bounding ON for the new links" Margin="0,10,0,0"/>
        <TextBlock TextWrapping="Wrap" Foreground="{StaticResource Muted}" FontSize="12" Margin="0,10,0,0"
                   Text="Files that are already linked in this project (same file name) are skipped. Relative paths need the project to be saved first."/>
      </StackPanel>
    </ScrollViewer>

    <Border Grid.Row="2" Background="{StaticResource RedTint}" BorderBrush="{StaticResource RedLine}"
            BorderThickness="0,1,0,0" Padding="18,9">
      <DockPanel>
        <Button x:Name="BtnCancel" DockPanel.Dock="Right" Style="{StaticResource OutlineBtn}"
                Content="Cancel" Margin="8,0,0,0" Padding="22,6"/>
        <Button x:Name="BtnGo" DockPanel.Dock="Right" Style="{StaticResource RedBtn}"
                Content="Link files" Margin="8,0,0,0" Padding="22,6"/>
        <TextBlock x:Name="StatusText" VerticalAlignment="Center" Foreground="{StaticResource Ink}"/>
      </DockPanel>
    </Border>
  </Grid>
</Window>
'''


PICK_XAML = u'''<Window @@NS@@
        Title="Copy to model" Height="460" Width="720" MinHeight="340" MinWidth="520"
        WindowStartupLocation="CenterOwner" Background="White"
        FontFamily="Segoe UI" FontSize="13" ShowInTaskbar="False">
  <Window.Resources>
@@STYLES@@
  </Window.Resources>
  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <Border Grid.Row="0" Background="{StaticResource HeaderBrush}" Padding="20,12">
      <StackPanel>
        <TextBlock Text="COPY TO MODEL" Foreground="White" FontSize="20" FontWeight="Bold"/>
        <TextBlock Text="Choose the target among the models open in this Revit session"
                   Foreground="White" Opacity="0.85" FontSize="12.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border Grid.Row="1" Margin="20,16,20,10" BorderBrush="{StaticResource RedLine}"
            BorderThickness="1" CornerRadius="6">
      <ListBox x:Name="ModelList" BorderThickness="0" SelectionMode="Extended" FontSize="13"/>
    </Border>
    <Border Grid.Row="2" Background="{StaticResource RedTint}" BorderBrush="{StaticResource RedLine}"
            BorderThickness="0,1,0,0" Padding="18,9">
      <DockPanel>
        <Button x:Name="BtnCancel" DockPanel.Dock="Right" Style="{StaticResource OutlineBtn}"
                Content="Cancel" Margin="8,0,0,0" Padding="22,6"/>
        <Button x:Name="BtnGo" DockPanel.Dock="Right" Style="{StaticResource RedBtn}"
                Content="Use selected" Margin="8,0,0,0" Padding="22,6"/>
        <TextBlock VerticalAlignment="Center" Foreground="{StaticResource Muted}"
                   Text="Ctrl / Shift + click to pick several. Targets stay open and unsaved."/>
      </DockPanel>
    </Border>
  </Grid>
</Window>
'''


COPY_XAML = u'''<Window @@NS@@
        Title="Copy to model" Height="640" Width="960" MinHeight="520" MinWidth="760"
        WindowStartupLocation="CenterOwner" Background="White"
        FontFamily="Segoe UI" FontSize="13" ShowInTaskbar="False">
  <Window.Resources>
@@STYLES@@
  </Window.Resources>
  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <Border Grid.Row="0" Background="{StaticResource HeaderBrush}" Padding="20,12">
      <StackPanel>
        <TextBlock Text="COPY LINKS TO MODEL" Foreground="White" FontSize="20" FontWeight="Bold"/>
        <TextBlock x:Name="TargetText" Foreground="White" Opacity="0.9" FontSize="12.5" Margin="0,3,0,0"
                   TextWrapping="Wrap"/>
      </StackPanel>
    </Border>
    <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto">
      <StackPanel Margin="20,14,20,6">
        <TextBlock Text="PREVIEW" Foreground="{StaticResource Red}" FontWeight="Bold"/>
        <TextBlock x:Name="SummaryText" Foreground="{StaticResource Muted}" Margin="0,2,0,8" TextWrapping="Wrap"/>
        <StackPanel x:Name="PreviewPanel" HorizontalAlignment="Left"/>
      </StackPanel>
    </ScrollViewer>
    <Border Grid.Row="2" BorderBrush="{StaticResource RedLine}" BorderThickness="0,1,0,0" Padding="20,10">
      <StackPanel>
        <TextBlock Text="IF A LINK ALREADY EXISTS IN THE TARGET" Foreground="{StaticResource Muted}"
                   FontSize="11" FontWeight="Bold"/>
        <WrapPanel Margin="0,2,0,6">
          <RadioButton x:Name="RbSkip" GroupName="Policy" Style="{StaticResource RedRadio}" IsChecked="True"
                       Content="Skip it" Margin="0,4,26,4"/>
          <RadioButton x:Name="RbAdd" GroupName="Policy" Style="{StaticResource RedRadio}"
                       Content="Add only the instances that are missing (same position = already there)"/>
        </WrapPanel>
        <CheckBox x:Name="ChkUnsharedExact" Style="{StaticResource RedCheck}" IsChecked="True"
                  Content="Instances with no shared site keep their exact current location (instead of origin to origin)"/>
        <TextBlock Foreground="{StaticResource Muted}" FontSize="11.5" TextWrapping="Wrap" Margin="26,6,0,0"
                   Text="Instances on a shared site use Revit's shared placement. Nothing is published, acquired or saved: the targets stay open and unsaved, and the whole copy is one Undo step in each target."/>
      </StackPanel>
    </Border>
    <Border Grid.Row="3" Background="{StaticResource RedTint}" BorderBrush="{StaticResource RedLine}"
            BorderThickness="0,1,0,0" Padding="18,9">
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="BtnCancel" Style="{StaticResource OutlineBtn}" Content="Cancel" Padding="22,6"/>
        <Button x:Name="BtnContinue" Style="{StaticResource RedBtn}" Content="Copy" Padding="26,6" Margin="0,3,0,3"/>
      </StackPanel>
    </Border>
  </Grid>
</Window>
'''


def _build(template):
    return template.replace("@@NS@@", NS).replace("@@STYLES@@", STYLES)


def main_xaml():
    return _build(MAIN_XAML)


def link_xaml():
    return _build(LINK_XAML)


def pick_xaml():
    return _build(PICK_XAML)


def copy_xaml():
    return _build(COPY_XAML)
