' Run a command completely hidden (no window, runs in background)
' Usage: wscript run-hidden.vbs "command" "args" "workingdir" "logfile"

If WScript.Arguments.Count < 2 Then
    WScript.Quit 1
End If

Dim cmd, args, workdir, logfile
cmd = WScript.Arguments(0)
args = WScript.Arguments(1)

If WScript.Arguments.Count >= 3 Then
    workdir = WScript.Arguments(2)
Else
    workdir = ""
End If

If WScript.Arguments.Count >= 4 Then
    logfile = WScript.Arguments(3)
Else
    logfile = ""
End If

Dim fso, shell, tempBatchFile, batchContent
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Create a temporary batch file to run the command
Dim timestamp
timestamp = Year(Now) & Month(Now) & Day(Now) & Hour(Now) & Minute(Now) & Second(Now) & Timer()
tempBatchFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\run_" & timestamp & ".bat"

' Build batch file content
batchContent = "@echo off" & vbCrLf

' Change directory if specified
If workdir <> "" Then
    batchContent = batchContent & "cd /d """ & workdir & """" & vbCrLf
End If

' Build command with redirection if logfile specified
If logfile <> "" Then
    batchContent = batchContent & """" & cmd & """ " & args & " > """ & logfile & """ 2>&1"
Else
    batchContent = batchContent & """" & cmd & """ " & args
End If

' Write batch file
Dim batFile
Set batFile = fso.CreateTextFile(tempBatchFile, True)
batFile.Write batchContent
batFile.Close

' Run the batch file hidden and don't wait
shell.Run tempBatchFile, 0, False

' Don't delete the batch file - let it run and clean up later
' The temp folder will auto-clean eventually

Set batFile = Nothing
Set fso = Nothing
Set shell = Nothing
