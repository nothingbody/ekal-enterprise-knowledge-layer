!macro customUnInstall
  ; Ask user whether to remove application data
  MessageBox MB_YESNO "是否同时删除所有用户数据（数据库、上传文件、向量索引、日志等）？$\n$\n选择「是」将彻底清除，无法恢复。$\n选择「否」仅卸载程序，保留数据以便将来重新安装后继续使用。" IDYES _removeData IDNO _skipData

  _removeData:
    ; Remove userData directory: %APPDATA%\rag-platform-desktop
    RMDir /r "$APPDATA\rag-platform-desktop"
    Goto _done

  _skipData:

  _done:
!macroend
