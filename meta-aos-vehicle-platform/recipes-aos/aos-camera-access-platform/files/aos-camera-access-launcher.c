/* SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE
#include <grp.h>
#include <limits.h>
#include <pwd.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *root = "/var/aos/workdirs/sm/runtimes/systemd-slot-camera-access";
static int safe_file(const char *path, int executable) {
    struct stat s;
    return lstat(path, &s) == 0 && S_ISREG(s.st_mode) && s.st_uid == 0 &&
        !(s.st_mode & 0022) && (!executable || access(path, X_OK) == 0);
}
int main(int argc, char **argv) {
    char slot[16], path[PATH_MAX], entry[PATH_MAX], config[PATH_MAX];
    const char *operation = NULL;
    struct passwd *u = getpwnam("aos-camera-access");
    struct group *g = getgrnam("aos-camera-read");
    if (!u || !g || !u->pw_uid || !g->gr_gid || getuid() != u->pw_uid ||
        geteuid() != u->pw_uid || getgid() != g->gr_gid || getegid() != g->gr_gid)
        goto fail;
    if (argc == 3 && !strcmp(argv[1], "--self-test") &&
        (!strcmp(argv[2], "a") || !strcmp(argv[2], "b"))) {
        snprintf(slot, sizeof(slot), "slots/%s", argv[2]); operation = "--self-test";
    } else if (argc == 1 || (argc == 2 && !strcmp(argv[1], "--mark-unavailable"))) {
        snprintf(path, sizeof(path), "%s/active", root);
        ssize_t n = readlink(path, slot, sizeof(slot)-1);
        if (n < 0 || n >= (ssize_t)sizeof(slot)-1) goto fail;
        slot[n] = 0;
        if (strcmp(slot, "slots/a") && strcmp(slot, "slots/b")) goto fail;
        if (argc == 2) operation = "--mark-unavailable";
    } else goto fail;
    snprintf(path, sizeof(path), "%s/%s", root, slot);
    struct stat s;
    if (lstat(path, &s) || !S_ISDIR(s.st_mode) || s.st_uid || (s.st_mode & 0022)) goto fail;
    snprintf(entry, sizeof(entry), "%s/%s/bin/camera-access", root, slot);
    snprintf(config, sizeof(config), "%s/%s/config/camera.json", root, slot);
    if (!safe_file(entry, 1) || !safe_file(config, 0) || prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) goto fail;
    char *arguments[] = {entry, "--config", config, (char *)operation, NULL};
    execv(entry, arguments);
fail:
    fputs("CAMERA_ACCESS_LAUNCH_FAILED\n", stderr);
    return 1;
}
