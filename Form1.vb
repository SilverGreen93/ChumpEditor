Public Class Form1

    Dim fileList As New List(Of String)

    Private Sub Form1_DragDrop(sender As Object, e As DragEventArgs) Handles Me.DragDrop
        Dim files As String() = e.Data.GetData(DataFormats.FileDrop)
        For Each file As String In files
            ListBox1.Items.Add(file)
            ListBox1.SelectedIndex = ListBox1.Items.Count - 1
            fileList.Add(file)
        Next
    End Sub

    Private Sub Form1_DragEnter(sender As Object, e As DragEventArgs) Handles Me.DragEnter
        If e.Data.GetDataPresent(DataFormats.FileDrop) Then
            e.Effect = DragDropEffects.Copy
        End If
    End Sub

    ''' <summary>
    ''' Transforms string kuid to 8 byte kuid (for routes/sessions)
    ''' </summary>
    ''' <param name="kuid">The kuid as string</param>
    ''' <returns>The kuid as 8 bytes</returns>
    ''' <remarks></remarks>
    Function KuidToHex(ByVal kuid As String) As Byte()
        Dim num(2) As Integer                           'variable to store kuid parts
        Dim ubytes(3), cbytes(3) As Byte                'user bytes and content bytes
        Dim str() As String                             'split kuid to tokens
        Dim rbytes(7) As Byte                           'returned bytes

        If kuid = "" Then
            'MessageBox.Show("NULL kuid encountered!", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            'err = True
            Return {0, 0, 0, 0, 0, 0, 0, 0}
        End If

        str = System.Text.RegularExpressions.Regex.Split(kuid, ":")

        If str.Length < 3 Then
            'MessageBox.Show("Invalid kuid encountered!", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return {0, 0, 0, 0, 0, 0, 0, 0}
        End If

        Try
            'parse the kuid parts (skip first) and convert to integers
            For i As Integer = 1 To str.Length - 1
                num(i - 1) = Val(str(i))
            Next

            'get the bytes from integers
            ubytes = BitConverter.GetBytes(num(0))
            cbytes = BitConverter.GetBytes(num(1))
            If (num(2) > 0 AndAlso num(2) < 128 AndAlso num(0) >= 0) Then 'check if uid is negative
                ubytes(3) = ubytes(3) Xor (CByte(num(2)) << 1)  'add the version number to byte 4 of uid
            End If

            'merge bytes
            For i As Integer = 0 To 3
                rbytes(i) = ubytes(i)
                rbytes(i + 4) = cbytes(i)
            Next
        Catch ex As Exception
            MessageBox.Show(ex.ToString, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try

        Return rbytes

    End Function

    ''' <summary>
    ''' Reverses the UID with the CID (for map files)
    ''' </summary>
    ''' <param name="kuid">The kuid as 8 bytes</param>
    ''' <returns>The reversed kuid as 8 bytes</returns>
    ''' <remarks></remarks>
    Function revKuid(ByVal kuid As Byte()) As Byte()

        Dim rbytes(7) As Byte   'returned bytes

        Try
            'reverse bytes (a-b-c-d-e-f-g-h -> e-f-g-h-a-b-c-d)
            For i As Integer = 0 To 3
                rbytes(i) = kuid(i + 4)
                rbytes(i + 4) = kuid(i)
            Next
        Catch ex As Exception
            MessageBox.Show(ex.ToString, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try

        Return rbytes

    End Function

    Function HexToKuid(ByVal kuid As Byte()) As String
        Dim rstring As String = "<kuid"
        Dim ubytes(3), cbytes(3) As Byte
        Dim version As Integer
        Dim uInt As Integer

        Array.Copy(kuid, 0, ubytes, 0, 4)
        Array.Copy(kuid, 4, cbytes, 0, 4)

        If (ubytes(3) And (1 << 0)) <> 0 Then
            'negative user id, ignore version
            version = 0
        Else
            version = Convert.ToInt32(ubytes(3) >> 1)
            ubytes(3) = ubytes(3) And &H01
        End If

        uInt = BitConverter.ToInt32(ubytes, 0)

        If version <> 0 Then
            rstring = rstring & "2:"
        Else
            rstring = rstring & ":"
        End If

        rstring = rstring & uInt
        rstring = rstring & ":"
        rstring = rstring & BitConverter.ToInt32(cbytes, 0)

        If version <> 0 Then
            rstring = rstring & ":" & version
        End If

        rstring = rstring & ">"
        Return rstring
    End Function

    Sub ParseSubTags(ByRef bytes As Byte(), ByRef fpointer As Integer, ByRef expandedChump As String, ByVal level As Integer)
        Dim tagLength As Integer = ParseInteger32(bytes, fpointer)
        fpointer = fpointer + 4
        Dim tagNameSize As Byte = bytes(fpointer)
        fpointer = fpointer + 1

        Dim tagName(tagNameSize - 2) As Byte
        Array.Copy(bytes, fpointer, tagName, 0, tagNameSize - 1)
        fpointer = fpointer + tagNameSize

        expandedChump = expandedChump & Space(level * 2) & System.Text.Encoding.UTF8.GetString(tagName)

        Dim tagType As Byte = bytes(fpointer)
        fpointer = fpointer + 1

        Select Case tagType
            Case 0 'container
                expandedChump = expandedChump & vbCrLf & Space(level * 2) & "{" & vbCrLf
                Dim currentFilePointer As Integer = fpointer
                While Not fpointer = currentFilePointer + tagLength - tagNameSize - 2

                    ParseSubTags(bytes, fpointer, expandedChump, level + 1)

                End While
                expandedChump = expandedChump & Space(level * 2) & "}"
            Case 1 'integer
                expandedChump = expandedChump &
                    Space(IIf(40 - tagNameSize - 1 - level * 2 < 2, 2, 40 - tagNameSize - 1 - level * 2))
                Dim comma As Boolean = False
                For i As Integer = 0 To tagLength - tagNameSize - 3 Step 4
                    expandedChump = expandedChump & IIf(comma, ",", "") & ParseInteger32(bytes, fpointer + i).ToString("G", Globalization.CultureInfo.InvariantCulture)
                    comma = True
                Next
            Case 2 'float
                expandedChump = expandedChump &
                    Space(IIf(40 - tagNameSize - 1 - level * 2 < 2, 2, 40 - tagNameSize - 1 - level * 2))
                Dim comma As Boolean = False
                For i As Integer = 0 To tagLength - tagNameSize - 3 Step 4
                    expandedChump = expandedChump & IIf(comma, ",", "") & ParseFloat(bytes, fpointer + i).ToString("G", Globalization.CultureInfo.InvariantCulture)
                    comma = True
                Next
            Case 3 'string
                If tagLength - tagNameSize - 4 > 0 Then 'otherwise it is a null string (not even a character)
                    Dim tagString(tagLength - tagNameSize - 4) As Byte
                    Array.Copy(bytes, fpointer, tagString, 0, tagLength - tagNameSize - 3)
                    expandedChump = expandedChump &
                        Space(IIf(40 - tagNameSize - 1 - level * 2 < 2, 2, 40 - tagNameSize - 1 - level * 2)) &
                        """" & System.Text.Encoding.UTF8.GetString(tagString) & """"
                End If
            Case 4 'binary
                If tagLength - tagNameSize - 4 > 0 Then 'otherwise it is a null string (not even a character)
                    Dim tagString(tagLength - tagNameSize - 4) As Byte
                    Array.Copy(bytes, fpointer, tagString, 0, tagLength - tagNameSize - 3)
                    expandedChump = expandedChump &
                    Space(IIf(40 - tagNameSize - 1 - level * 2 < 2, 2, 40 - tagNameSize - 1 - level * 2)) &
                    System.Text.Encoding.ASCII.GetString(tagString)
                End If
            Case 5 'null

            Case 13 'kuid
                Dim kuid(7) As Byte
                Array.Copy(bytes, fpointer, kuid, 0, 8)
                expandedChump = expandedChump &
                    Space(IIf(40 - tagNameSize - 1 - level * 2 < 2, 2, 40 - tagNameSize - 1 - level * 2)) &
                    HexToKuid(kuid)
            Case Else
                Throw New Exception("Unknown tag type: " & tagType)
        End Select

        If tagType <> 0 Then fpointer = fpointer + tagLength - tagNameSize - 2
        expandedChump = expandedChump & vbCrLf
    End Sub

    Private Sub Button1_Click(sender As Object, e As EventArgs) Handles Button1.Click

        Dim currentChump As Integer = 0

        For Each file As String In fileList

            If My.Computer.FileSystem.FileExists(file) Then 'expand chump

                'Try

                Dim bytes As Byte() = My.Computer.FileSystem.ReadAllBytes(file)

                    Dim b1(3) As Byte
                    Array.Copy(bytes, b1, 4)
                    Dim b2 As Byte() = System.Text.Encoding.ASCII.GetBytes("ACS$")

                    If Not CompareBytes(b1, b2) Then
                        MessageBox.Show("File format not supported for " & file)
                        Continue For
                    End If

                    Dim fpointer As Integer = 12
                    Dim chumpLength As Integer = ParseInteger32(bytes, fpointer)
                    fpointer = fpointer + 4

                    Dim expandedChump As String = vbCrLf

                    Dim currentFilePointer As Integer = fpointer
                    Dim level As Integer = 0
                    While Not fpointer = currentFilePointer + chumpLength

                        ParseSubTags(bytes, fpointer, expandedChump, level)

                    End While

                    My.Computer.FileSystem.WriteAllText(System.IO.Path.GetDirectoryName(file) & "\" & System.IO.Path.GetFileNameWithoutExtension(file) & ".txt", expandedChump, False)

                    currentChump = currentChump + 1

                'Catch ex As Exception
                '    MessageBox.Show(ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                'End Try

            End If
        Next
        MessageBox.Show("Finished expanding chumps.", "Ready", MessageBoxButtons.OK, MessageBoxIcon.Information)
    End Sub

    Function CompareBytes(ByVal b1 As Byte(), ByVal b2 As Byte()) As Boolean
        If (b1 Is b2) Then
            Return True
        End If
        If (b1 Is Nothing OrElse b2 Is Nothing) Then
            Return False
        End If
        If (b1.Length <> b2.Length) Then
            Return False
        End If
        For i As Integer = 0 To b1.Length - 1
            If (b1(i) <> b2(i)) Then
                Return False
            End If
        Next i
        Return True
    End Function

    Function FormatHex(ByRef b As Byte(), ByVal start As Integer, ByVal len As Integer) As Byte()

        Dim rbytes(len - 1) As Byte   'returned bytes

        For i As Integer = 0 To len - 1
            rbytes(i) = b(start + i)
        Next

        Return rbytes

    End Function

    Function ParseInteger32(ByRef b As Byte(), ByVal pos As Integer) As Integer
        Return BitConverter.ToInt32(FormatHex(b, pos, 4), 0)
    End Function

    Function ParseInteger64(ByRef b As Byte(), ByVal pos As Integer) As Long
        Return BitConverter.ToInt64(FormatHex(b, pos, 8), 0)
    End Function

    Function ParseFloat(ByRef b As Byte(), ByVal pos As Integer) As Single
        Return BitConverter.ToSingle(FormatHex(b, pos, 4), 0)
    End Function

    Function ToInteger32(ByVal i As Integer) As Byte()
        Return FormatHex(BitConverter.GetBytes(i), 0, 4)
    End Function

    Function ToInteger64(ByVal i As Long) As Byte()
        Return FormatHex(BitConverter.GetBytes(i), 0, 8)
    End Function

    Function ToFloat(ByVal i As Single) As Byte()
        Return FormatHex(BitConverter.GetBytes(i), 0, 4)
    End Function

    Private Sub Button3_Click(sender As Object, e As EventArgs) Handles Button3.Click
        If ListBox1.SelectedItem = Nothing Then Exit Sub
        fileList.RemoveAt(ListBox1.SelectedIndex)
        ListBox1.Items.RemoveAt(ListBox1.SelectedIndex)
        ListBox1.SelectedIndex = ListBox1.Items.Count - 1
    End Sub


    Private Sub Button4_Click(sender As Object, e As EventArgs) Handles Button4.Click
        ListBox1.Items.Clear()
        fileList.Clear()

    End Sub

    Private Sub Form1_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        Dim files As String() = My.Application.CommandLineArgs.ToArray
        For Each file As String In files
            ListBox1.Items.Add(file)
            ListBox1.SelectedIndex = ListBox1.Items.Count - 1
            fileList.Add(file)
        Next
    End Sub

    Private Sub LinkLabel1_LinkClicked(sender As Object, e As LinkLabelLinkClickedEventArgs) Handles LinkLabel1.LinkClicked
        Process.Start("http://vvmm.freeforums.org/")
    End Sub

    'a new instance of the application was started with new arguments
    Public Sub NewArgumentsReceived(args As String())
        If args.Length > 0 Then
            Dim files As String() = args.ToArray
            For Each file As String In files
                ListBox1.Items.Add(file)
                ListBox1.SelectedIndex = ListBox1.Items.Count - 1
                fileList.Add(file)
            Next
        End If
    End Sub

End Class
