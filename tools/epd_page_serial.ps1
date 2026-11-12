Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# SAM | 2026-10-11 11:45 +08:00 | Add a dependency-free Windows host tool
# because the target PC may not have Python or pyserial installed.
$script:port = $null
$form = New-Object Windows.Forms.Form
$form.Text = 'YP001 LVGL 页面切换'
$form.Size = New-Object Drawing.Size(650, 470)
$form.StartPosition = 'CenterScreen'

$ports = New-Object Windows.Forms.ComboBox
$ports.Location = New-Object Drawing.Point(20, 20)
$ports.Size = New-Object Drawing.Size(120, 25)
[IO.Ports.SerialPort]::GetPortNames() | ForEach-Object { [void]$ports.Items.Add($_) }
if ($ports.Items.Count -gt 0) { $ports.SelectedIndex = 0 }
$form.Controls.Add($ports)

$open = New-Object Windows.Forms.Button
$open.Text = '打开串口'; $open.Location = New-Object Drawing.Point(155, 20)
$open.Size = New-Object Drawing.Size(100, 25); $form.Controls.Add($open)
$status = New-Object Windows.Forms.Label
$status.Text = '未连接（115200 / 8N1）'; $status.Location = New-Object Drawing.Point(275, 24)
$status.AutoSize = $true; $form.Controls.Add($status)
$log = New-Object Windows.Forms.TextBox
$log.Multiline = $true; $log.ScrollBars = 'Vertical'; $log.ReadOnly = $true
$log.Location = New-Object Drawing.Point(20, 285); $log.Size = New-Object Drawing.Size(590, 125)
$form.Controls.Add($log)
function Add-Log([string]$text) { $log.AppendText("$(Get-Date -Format HH:mm:ss) $text`r`n") }
$buttons = @(
    @('默认 IMEI/二维码', 'screen'), @('主页', 'screen_main'), @('时间页', 'screen_time'),
    @('低电页', 'screen_lowbat'), @('呼叫中', 'screen_calling'), @('呼叫结束', 'screen_callend')
)
for ($i = 0; $i -lt $buttons.Count; $i++) {
    $b = New-Object Windows.Forms.Button
    $b.Text = "$($buttons[$i][0])  ($($buttons[$i][1]))"; $b.Tag = $buttons[$i][1]
    $b.Location = New-Object Drawing.Point((20 + (($i % 2) * 300)), (70 + ([math]::Floor($i / 2) * 65)))
    $b.Size = New-Object Drawing.Size(280, 45)
    $b.Add_Click({
        if ($null -eq $script:port -or -not $script:port.IsOpen) { [Windows.Forms.MessageBox]::Show('请先打开串口'); return }
        $cmd = "epd_page $($this.Tag)`r"; $script:port.Write($cmd); Add-Log(">> $($cmd.Trim())")
    })
    $form.Controls.Add($b)
}
$open.Add_Click({
    if ($null -ne $script:port -and $script:port.IsOpen) { $script:port.Close(); $script:port = $null; $open.Text = '打开串口'; $status.Text = '未连接（115200 / 8N1）'; return }
    if ([string]::IsNullOrWhiteSpace($ports.Text)) { [Windows.Forms.MessageBox]::Show('未发现串口，请连接汇顶 UART0'); return }
    try {
        $script:port = New-Object IO.Ports.SerialPort($ports.Text, 115200, ([IO.Ports.Parity]::None), 8, ([IO.Ports.StopBits]::One))
        $script:port.DtrEnable = $false; $script:port.RtsEnable = $false; $script:port.Open()
        $open.Text = '关闭串口'; $status.Text = "已连接 $($ports.Text)（115200 / 8N1）"; Add-Log('串口已打开')
    } catch { [Windows.Forms.MessageBox]::Show("打开失败：$($_.Exception.Message)") }
})
$form.Add_FormClosed({ if ($null -ne $script:port -and $script:port.IsOpen) { $script:port.Close() } })
[void]$form.ShowDialog()
