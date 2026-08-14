/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *const root = "/var/aos/workdirs/sm/runtimes/systemd-slot-component";

static int fail(const char *message)
{
    fprintf(stderr, "Vehicle data provider launcher: %s\n", message);
    return 1;
}

int main(void)
{
    char        link_path[PATH_MAX];
    char        resolved[PATH_MAX];
    char        executable[PATH_MAX];
    char        config[PATH_MAX];
    struct stat status;

    const int active_length = snprintf(link_path, sizeof(link_path), "%s/active", root);
    if (active_length < 0 || (size_t)active_length >= sizeof(link_path)) {
        return fail("active path is too long");
    }

    const ssize_t length = readlink(link_path, resolved, sizeof(resolved) - 1);
    if (length < 0) {
        return fail("no active component slot");
    }
    resolved[length] = '\0';
    if (strcmp(resolved, "slots/a") != 0 && strcmp(resolved, "slots/b") != 0) {
        return fail("active slot target is invalid");
    }

    if (snprintf(executable, sizeof(executable), "%s/%s/bin/vehicle-data-provider", root, resolved)
            >= (int)sizeof(executable)
        || snprintf(config, sizeof(config), "%s/%s/config/provider.json", root, resolved) >= (int)sizeof(config)) {
        return fail("component path is too long");
    }

    if (lstat(executable, &status) != 0 || !S_ISREG(status.st_mode) || status.st_uid != 0
        || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0 || access(executable, X_OK) != 0) {
        return fail("component executable failed ownership or permission checks");
    }
    if (lstat(config, &status) != 0 || !S_ISREG(status.st_mode) || status.st_uid != 0
        || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        return fail("component configuration failed ownership or permission checks");
    }

    if (setenv("AOS_VEHICLE_DATA_PROVIDER_ROOT", root, 1) != 0) {
        return fail("cannot set the provider root environment");
    }

    char *const arguments[] = {executable, "--config", config, NULL};
    execv(executable, arguments);

    fprintf(stderr, "Vehicle data provider launcher: exec failed: %s\n", strerror(errno));
    return 1;
}
