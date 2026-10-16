#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CLOUD_SHELL_UID 1000
#define CLOUD_SHELL_GID 1000
#define PYTHON_BIN "/opt/openstack/bin/python"
#define BOOTSTRAP_SCRIPT "/usr/local/libexec/afterglow-cloud-shell-bootstrap.py"

static int valid_term(const char *value) {
    size_t length;

    if (value == NULL) {
        return 0;
    }
    length = strlen(value);
    if (length == 0 || length > 64) {
        return 0;
    }
    for (size_t index = 0; index < length; index++) {
        char current = value[index];
        if (!((current >= 'a' && current <= 'z') ||
              (current >= 'A' && current <= 'Z') ||
              (current >= '0' && current <= '9') ||
              current == '-' || current == '_' || current == '.')) {
            return 0;
        }
    }
    return 1;
}

int main(int argc, char **argv) {
    const char *original_term;
    char term[65] = "xterm-256color";

    (void)argv;
    if (argc != 1 || getuid() != CLOUD_SHELL_UID || geteuid() != 0 || getegid() != CLOUD_SHELL_GID) {
        fputs("Cloud Shell bootstrap denied.\n", stderr);
        return 126;
    }

    original_term = getenv("TERM");
    if (valid_term(original_term)) {
        memcpy(term, original_term, strlen(original_term) + 1);
    }
    if (clearenv() != 0 ||
        setenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", 1) != 0 ||
        setenv("TERM", term, 1) != 0 ||
        setenv("PYTHONUNBUFFERED", "1", 1) != 0) {
        fputs("Cloud Shell bootstrap failed.\n", stderr);
        return 126;
    }
    if (setgroups(0, NULL) != 0 || setresgid(0, 0, 0) != 0 || setresuid(0, 0, 0) != 0) {
        fputs("Cloud Shell bootstrap failed.\n", stderr);
        return 126;
    }

    execl(PYTHON_BIN, "python", "-I", BOOTSTRAP_SCRIPT, (char *)NULL);
    fprintf(stderr, "Cloud Shell bootstrap failed (%d).\n", errno);
    return 126;
}
