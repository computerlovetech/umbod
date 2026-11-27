---
description: Give groups a shared file workspace, share single files and folders, and let agents read and write them.
---

# Files

People and agents work on the same files. Files live in namespaces:

| Namespace | Who has access |
| --- | --- |
| **My files** | Only you. Created the first time you use it |
| A shared namespace | The groups an administrator assigns |

Use a shared namespace when a group needs the same files. Use a share when one person or group needs one file or folder.

## Create a shared namespace

You need to be an administrator.

1. Open **Administration → Shared namespaces** and choose **+**. Give it a name and, optionally, a description.
2. Open **Administration → Permissions → Filesystem** and select a group.
3. Choose **Read** or **Read and write** for the namespace.
4. Choose **Save permissions**.

A new namespace has no group access until you finish steps 2 to 4.

**Check:** sign in as a member of the group and find the namespace under **Files → Shared namespaces**.

| Permission | Allows |
| --- | --- |
| Read | Browse and read |
| Read and write | Also create, upload, rename, move, edit descriptions, and delete files |

Administrators manage namespaces without seeing their contents. To browse one, you need to be in an assigned group yourself.

## Share a file or folder

1. Open the item's actions and choose **Share**.
2. Add groups or users and choose their permission.
3. For a folder, **Include contents** also shares everything in it, now and later.

**Check:** the recipient finds the item under **Files → Shared with me**.

Permissions add up. Removing a share does not remove access the person has through a namespace or another share.

## What you can do with files

| Action | Rules |
| --- | --- |
| Upload | One file at a time, 10 MiB by default. A name that already exists is rejected, not overwritten |
| Preview | Markdown, PDF, and common image formats |
| Rename and move | Within one namespace. Moving between namespaces is not supported |
| Delete | Files only. Folders cannot be deleted. A shared namespace can be deleted when it is empty |

## Agents and files

Agents use the same files through the MCP endpoint, with the permissions of the signed-in user. They can browse, read, create, upload, rename, move, and share. Deleting a file asks the user for approval first.

The tools are described in [Built-in MCP tools](../reference/built-in-tools.md#filesystem-tools), and the HTTP endpoints in the [REST API](../reference/rest-api.md#files).

## If a file or location is missing

1. Check **Files → Locations** as the affected user, not as an administrator.
2. For a shared namespace: check the group's permission and that you chose **Save permissions**.
3. For a share: check that it still exists. **Shared with me** lists only items shared directly, so open the shared folder to find its contents.
4. If **Upload file** or **New folder** is unavailable, the user has read access only.
