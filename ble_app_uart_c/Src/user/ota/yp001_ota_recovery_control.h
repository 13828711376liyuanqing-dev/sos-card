#ifndef YP001_OTA_RECOVERY_CONTROL_H
#define YP001_OTA_RECOVERY_CONTROL_H
/* SAM | 2026-10-27 +08:00 | A protected PREPARED GR task may observe status or relay this R6's explicit recovery request. This is transport admission, never a ticket/activation grant. */
#include <stdbool.h>
#include <string.h>
static inline bool yp001_ota_recovery_command_allowed(const char *command)
{
    static const char prefix[]="OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4";
    size_t n=sizeof(prefix)-1u;
    if(!command)return false;
    if(!strcmp(command,"FOTA_STATUS"))return true;
    if(strncmp(command,prefix,n))return false;
    /* CAT's exact job/history validator remains the authority on which selector is actually authorized. This grammar cannot extend its quota. */
    return command[n]==0||(command[n]==','&&command[n+1]>='2'&&command[n+1]<='9'&&command[n+2]==0);
}
#endif
