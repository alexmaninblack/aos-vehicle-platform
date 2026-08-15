/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#define _GNU_SOURCE

#include <errno.h>
#include <grp.h>
#include <linux/capability.h>
#include <limits.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static const char *const root =
    "/var/aos/workdirs/sm/runtimes/systemd-slot-component";
static const char *const runtime_user = "aos-vdp";

static int fail(const char *message) {
  fprintf(stderr, "Vehicle data provider launcher: %s\n", message);
  return 1;
}

static int drop_launcher_privileges(void) {
  struct passwd *account = getpwnam(runtime_user);
  struct __user_cap_header_struct capability_header = {
      .version = _LINUX_CAPABILITY_VERSION_3,
      .pid = 0,
  };
  struct __user_cap_data_struct capability_data[_LINUX_CAPABILITY_U32S_3] = {0};

  if (account == NULL || account->pw_uid == 0 || account->pw_gid == 0) {
    return fail("dedicated runtime account is unavailable or unsafe");
  }
  const uid_t runtime_uid = account->pw_uid;
  const gid_t runtime_gid = account->pw_gid;

  if (initgroups(runtime_user, runtime_gid) != 0) {
    return fail("cannot restrict supplementary groups");
  }
  if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
    return fail("cannot enable no_new_privs");
  }
  if (setresgid(runtime_gid, runtime_gid, runtime_gid) != 0) {
    return fail("cannot drop runtime group privileges");
  }
  if (setresuid(runtime_uid, runtime_uid, runtime_uid) != 0) {
    return fail("cannot drop runtime user privileges");
  }
  if (getuid() == 0 || geteuid() == 0 || getgid() == 0 || getegid() == 0) {
    return fail("runtime identity remained privileged");
  }
  if (prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
    return fail("no_new_privs did not remain active");
  }
  if (syscall(SYS_capget, &capability_header, capability_data) != 0) {
    return fail("cannot verify the runtime capability set");
  }
  for (size_t index = 0; index < _LINUX_CAPABILITY_U32S_3; ++index) {
    if (capability_data[index].effective != 0 ||
        capability_data[index].permitted != 0 ||
        capability_data[index].inheritable != 0) {
      return fail("runtime capabilities were not cleared");
    }
  }

  return 0;
}

int main(int argc, char *argv[]) {
  char link_path[PATH_MAX];
  char selected_slot[16];
  char executable[PATH_MAX];
  char config[PATH_MAX];
  struct stat status;
  const char *operation = NULL;

  if (argc == 2 && strcmp(argv[1], "--mark-unavailable") == 0) {
    operation = "--mark-unavailable";
  } else if (argc == 3 && strcmp(argv[1], "--self-test") == 0 &&
             (strcmp(argv[2], "a") == 0 || strcmp(argv[2], "b") == 0)) {
    operation = "--self-test";
    if (snprintf(selected_slot, sizeof(selected_slot), "slots/%s", argv[2]) >=
        (int)sizeof(selected_slot)) {
      return fail("self-test slot is too long");
    }
  } else if (argc != 1) {
    return fail("operation is invalid");
  }

  if (operation == NULL || strcmp(operation, "--mark-unavailable") == 0) {
    const int active_length =
        snprintf(link_path, sizeof(link_path), "%s/active", root);
    if (active_length < 0 || (size_t)active_length >= sizeof(link_path)) {
      return fail("active path is too long");
    }

    const ssize_t length =
        readlink(link_path, selected_slot, sizeof(selected_slot) - 1);
    if (length < 0 || (size_t)length >= sizeof(selected_slot)) {
      return fail("no valid active component slot");
    }
    selected_slot[length] = '\0';
    if (strcmp(selected_slot, "slots/a") != 0 &&
        strcmp(selected_slot, "slots/b") != 0) {
      return fail("active slot target is invalid");
    }
  }

  if (snprintf(executable, sizeof(executable),
               "%s/%s/bin/vehicle-data-provider", root,
               selected_slot) >= (int)sizeof(executable) ||
      snprintf(config, sizeof(config), "%s/%s/config/provider.json", root,
               selected_slot) >= (int)sizeof(config)) {
    return fail("component path is too long");
  }

  if (lstat(executable, &status) != 0 || !S_ISREG(status.st_mode) ||
      status.st_uid != 0 || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0 ||
      access(executable, X_OK) != 0) {
    return fail("component executable failed ownership or permission checks");
  }
  if (lstat(config, &status) != 0 || !S_ISREG(status.st_mode) ||
      status.st_uid != 0 || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
    return fail(
        "component configuration failed ownership or permission checks");
  }

  if (setenv("AOS_VEHICLE_DATA_PROVIDER_ROOT", root, 1) != 0) {
    return fail("cannot set the provider root environment");
  }
  if (drop_launcher_privileges() != 0) {
    return 1;
  }

  if (operation == NULL) {
    char *const arguments[] = {executable, "--config", config, NULL};
    execv(executable, arguments);
  } else {
    char *const arguments[] = {executable, (char *)operation, "--config",
                               config, NULL};
    execv(executable, arguments);
  }

  fprintf(stderr, "Vehicle data provider launcher: exec failed: %s\n",
          strerror(errno));
  return 1;
}
