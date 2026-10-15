#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
static int fail(const wchar_t *message, DWORD code) {
    wchar_t detail[512];
    swprintf_s(detail, _countof(detail), L"%ls\nWindows error: %lu", message, (unsigned long)code);
    MessageBoxW(NULL, detail, L"予備品管理システム", MB_OK | MB_ICONERROR);
    return 1;
}
int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    wchar_t root[32768], child[32768], *end, *command;
    size_t size;
    DWORD n, status = 1;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    BOOL started;
    (void)inst; (void)prev; (void)show;
    n = GetModuleFileNameW(NULL, root, _countof(root));
    if (!n || n >= _countof(root)-1) return fail(L"ランチャーの保存場所を取得できません。", GetLastError());
    end = wcsrchr(root, L'\\');
    if (!end) return fail(L"ランチャーのフォルダが不明です。", ERROR_BAD_PATHNAME);
    *end = L'\0';
    if (wcslen(root) + wcslen(L"\\src\\SparePartsManagement.exe") + 1 >= _countof(child))
        return fail(L"アプリの保存場所が長すぎます。", ERROR_FILENAME_EXCED_RANGE);
    swprintf_s(child, _countof(child), L"%ls\\src\\SparePartsManagement.exe", root);
    if (GetFileAttributesW(child) == INVALID_FILE_ATTRIBUTES)
        return fail(L"src 内のアプリ本体がありません。ZIPを全展開してください。", ERROR_FILE_NOT_FOUND);
    if (!SetEnvironmentVariableW(L"SPARES_APP_ROOT", root))
        return fail(L"データ保存場所の指定に失敗しました。", GetLastError());
    if (!args) args = L"";
    size = wcslen(child) + wcslen(args) + 5;
    command = (wchar_t *)calloc(size, sizeof(wchar_t));
    if (!command) return fail(L"アプリの起動準備に失敗しました。", ERROR_OUTOFMEMORY);
    swprintf_s(command, size, L"\"%ls\" %ls", child, args);
    startup.cb = sizeof(startup);
    started = CreateProcessW(child, command, NULL, NULL, FALSE, 0, NULL, root, &startup, &process);
    free(command);
    if (!started) return fail(L"アプリ本体を起動できません。", GetLastError());
    if (WaitForSingleObject(process.hProcess, INFINITE) == WAIT_FAILED) {
        DWORD error = GetLastError();
        CloseHandle(process.hThread); CloseHandle(process.hProcess);
        return fail(L"アプリの終了を確認できません。", error);
    }
    GetExitCodeProcess(process.hProcess, &status);
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    return (int)status;
}
