#!/usr/bin/env python3

import os
import sys
import subprocess
import json
import logging
from loggery import hprint
import threading

# -------- Logging Setup --------
LOG_FILE = "main.log"
handler = logging.FileHandler(LOG_FILE)

# -------- Global Flags --------
DBG = False
EXECUTE_COMMANDS = True  # False = dry-run

# -------- Utility Functions --------

def run_cmd(cmd: list, desc: str = ""):
    """
    Run a system command safely.
    Honors dry-run mode.
    """
    hprint(f"Running: {' '.join(cmd)}", "debug", handler, "main")

    if not EXECUTE_COMMANDS:
        hprint(f"[DRY RUN] {desc}", "info", handler, "main")
        return 0

    try:
        result = subprocess.run(cmd, check=True)
        return result
    except subprocess.CalledProcessError as e:
        hprint(f"Command failed: {e}", "error", handler, "main")
        sys.exit(1)


def require_root():
    if os.geteuid() != 0:
        hprint("Please run as root.", "critical", handler, "main")
        sys.exit(1)


def detect_boot_mode():
    if os.path.exists("/sys/firmware/efi"):
        hprint("Detected UEFI system", "info", handler, "main")
        return "uefi"
    else:
        hprint("Detected BIOS system", "info", handler, "main")
        return "bios"


# -------- Stage Functions --------

def iso_stage(config):
    """
    Runs in ISO environment.
    Responsible for partitioning, pacstrap, genfstab.
    """
    hprint("Starting ISO stage", "info", handler, "main")


    #Network setup stage using NetworkManager
    def runping(hostname):
        """Runs a ping and if it fails, raises Exception "Returncode", otherwise returns True"""
        h=subprocess.run("ping -c 1 -w2 " + hostname + " >/dev/null 2>&1".split(" "))
        if h.returncode!=0:raise Exception("Returncode")
        return True

    hprint("Stage: Network setup", "info", handler, "main")
    count=0
    while True:
        try:
            if runping("google.com"):break
        except Exception as e:
            if str(e)=="Returncode":
                if count>=1:hprint("Networking has failed (google.com)")
                print("Trying direct-IP")
                try:
                    if runping("1.1.1.1"):break
                except Exception:
                    if str(e)=="Returncode":
                        if count>=1:hprint("Networking has still failed on direct-IP (1.1.1.1)")
                    else:
                        hprint(f"An error has occured in the script: {e}")
                        sys.exit(1)
            else:
                hprint(f"An error has occured in the script: {e}")
                sys.exit(1)

        print("KDE system settings will be opened, please press the plus to add a new connection, then close it, and press enter.")
        run_cmd(["systemsettings", "kcm_networkmanagement"])#Better to use nmcli probably
        input("Press enter, once you are done setting up the network")


    #Select disk stage
    hprint("Stage: Disk stage", "info", handler, "main")
    diskinfo={}
    while True:
        i=input("Automatic (a) (EVERYTHING WILL BE CLEARED!) or Manual (m): ")
        if i == "a":
            auto=True
            hprint("Automatic mode selected", "info", handler, "main")
        elif i == "m":
            auto=False
            hprint("Manual mode selected", "info", handler, "main")
        else:
            hprint("Invalid input", "error", handler, "main")
            continue
        break
    #TODO: Implement both
    if auto:
        while True:
            # Get parted output in JSON
            try:
                lsblk = subprocess.run(
                    ["parted", "-lj"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                hprint(f"Failed to execute parted: {e.stderr.strip()}", "error", handler, "main")
                continue

            try:
                parted_data = json.loads(lsblk.stdout)
            except json.JSONDecodeError:
                hprint("Failed to parse parted output as JSON.", "error", handler, "main")
                continue

            disks = []
            print("Do not install to the USB you are booted off or else this will break!")
            for entry in parted_data:
                disk = entry.get("disk", {})
                disks.append(disk)
                print(f"Path: {disk.get('path','N/A')} - Model: {disk.get('model','N/A')} - Size: {disk.get('size','N/A')} - Type: {disk.get('type','N/A')}")

            if not disks:
                hprint("No disks found! Please check your hardware.", "error", handler, "main")
                continue

            i = input("Select disk from the list above (use path): ").strip()
            selected_disk = next((d for d in disks if d.get('path') == i), None)

            if selected_disk is not None:
                path = selected_disk['path']
                hprint(f"Selected disk: {path}", "info", handler, "main")
                break
            else:
                hprint("Path incorrect. Please try again.", "error", handler, "main")

        #TODO: Get everything partitioned, using diskinfo['efi'], diskinfo['mainpartition']
        
    else:
        # Launch gparted if the user requests, otherwise prompt to continue
        while True:
            print("You have chosen manual mode.")
            print("Do you already have your partitions set up? (c)")
            print("Or open gparted for partitioning? (g)")
            i = input("(c/g): ").strip().lower()
            if i == "g":
                def open_gparted():
                    try:
                        subprocess.Popen(["gparted"])
                    except Exception as e:
                        print(f"Failed to open gparted: {e}")
                gparted_thread = threading.Thread(target=open_gparted, daemon=True)
                gparted_thread.start()
                print("\nOpened gparted in a new window. Please partition your disk and come back here.")
                input("Press Enter when you are done with gparted.")
                break
            elif i == "c":
                break
            else:
                print("Invalid option. Please enter 'c' or 'g'.")
                continue

        # Partition info to gather
        diskparts = [
            {"name": "Main Partition", "key": "mainpartition","mount":"/"},
            {"name": "EFI", "key": "efi","mount":"/boot/efi"},
        ]
        extraparts = []
        customparts = False

        # Ask about custom mount point partitions
        while True:
            i = input("Do you have any custom mount point partitions (e.g. /home)?\n"
                      "If not, just say 'n'. (y/n): ").strip().lower()
            if i == "y":
                customparts = True
                break
            elif i == "n":
                print("No custom /* partitions, OK.")
                break
            else:
                print(f"Invalid option '{i}'. Please enter 'y' or 'n'.")
                continue

        # Gather custom partitions if needed
        if customparts:
            print("Adding custom partitions (e.g. additional mount points).")
            print("Format: /dev/sdXY:/mountpoint (example: /dev/sda3:/home) (sdXY does not mean it is limited to /dev/sda1)")
            print("Type 'exit' to finish adding.")
            while True:
                inp = input("Type here: ").strip()
                if inp.lower() == "exit":
                    break
                parts = inp.split(":", 1)
                if len(parts) == 2:
                    dev, mountpoint = parts
                    dev = dev.strip()
                    mountpoint = mountpoint.strip()
                    if not dev.startswith("/") or not mountpoint.startswith("/"):
                        print("Both device and mount point must start with '/'. Please try again.")
                        continue
                    if not os.path.exists(dev):
                        print(f"Device {dev} does not exist. Please try again.")
                        continue
                    extraparts.append({"bdevpath": dev, "path": mountpoint})
                    print(f"Added: {dev} -> {mountpoint}")
                else:
                    print("Invalid format. Please use /dev/sdXY:/mountpoint.")

        # Get required partition paths
        diskinfo = {}
        for part in diskparts:
            while True:
                path = input(f"Enter the device path for {part['name']} (e.g., /dev/sda1): ").strip()
                if path and path.startswith("/"):
                    if not os.path.exists(path):
                        print(f"Partition path {path} does not exist. Please try again.")
                        continue
                    diskinfo[part["key"]] = path
                    print(f"{part['name']} selected: {path}")
                    break
                else:
                    print("No valid partition path entered. Please try again.")
                    continue

    #Mounting
    print("\n--- Mounting selected partitions ---")
    run_cmd(["mkdir","/target"],"Make /target")
    for key, device in diskinfo.items():
        # Identify mountpoint from diskparts by key
        mountpoint = None
        for part in diskparts:
            if part["key"] == key:
                mountpoint = "/target"+part["mount"]
                break
        if mountpoint:
            # We create the mountpoint if it doesn't exist
            if not os.path.exists(mountpoint):
                run_cmd(["mkdir", "-p", mountpoint], f"Create mountpoint {mountpoint}")
            run_cmd(["mount", device, mountpoint], f"Mounting {device} to {mountpoint}")
        else:
            print(f"Warning: No mount point found for partition key '{key}'. Skipping.")
    # Mount any extra partitions (custom ones)
    if 'extraparts' in locals():
        for part in extraparts:
            mountpoint = "/target"+part["path"]
            device = part["bdevpath"]
            if not os.path.exists(mountpoint):
                run_cmd(["mkdir", "-p", mountpoint], f"Create mountpoint {mountpoint} (extra)")
            run_cmd(["mount", device, mountpoint], f"Mounting {device} to {mountpoint} (extra)")

    #Hostname selection
    import re

    def is_valid_hostname(hostname):
        # Hostname must be 1-253 characters overall
        if len(hostname) == 0 or len(hostname) > 253:
            return False
        # No segment should be > 63 chars, and must match allowed chars
        allowed = re.compile(r'^[a-zA-Z0-9-]+$')
        if hostname.startswith('-') or hostname.endswith('-'):
            return False
        if '..' in hostname:
            return False
        labels = hostname.split('.')
        for label in labels:
            if len(label) == 0 or len(label) > 63:
                return False
            if not allowed.match(label):
                return False
            if label.startswith('-') or label.endswith('-'):
                return False
        return True

    while True:
        i = input("Input your hostname here: ").strip()
        if is_valid_hostname(i):
            print(f"Hostname set to: {i}")
            config['hostname'] = i
            break
        else:
            print(
                "Hostname is incorrect.\n"
                "Rules:\n"
                "- Each label (part between dots) is 1 to 63 characters long.\n"
                "- The full hostname (including dots) is at most 253 characters long.\n"
                "- Only letters a-z, A-Z, digits 0-9, and hyphens (-) are allowed.\n"
                "- No segment may start or end with a hyphen.\n"
                "- Hostname may not start or end with a hyphen.\n"
                "- Use dots (.) for domain sections if needed.\n"
                "- No empty segments (no double dots).\n"
            )

    # User
    import re
    def is_valid_username(username):
        # Username must be 1-32 chars, start with lowercase letter, contain only [a-z0-9_-]
        if not username:
            return False
        if len(username) < 1 or len(username) > 32:
            return False
        if not re.match(r'^[a-z_][a-z0-9_-]*$', username):
            return False
        # Don't allow user names ending with a dash or underscore
        if username[-1] in '-_':
            return False
        # Reserved names
        if username in ['root', 'daemon', 'bin', 'sys', 'sync', 'games', 'man', 'lp', 'mail', 'news', 'uucp', 'proxy', 'www-data', 'backup', 'list', 'irc', 'gnats', 'nobody']:
            return False
        return True

    config["username"]={}
    while True:
        i = input("Enter a username (1-32 chars, lower-case, [a-z0-9_-], must start with letter): ").strip()
        if is_valid_username(i):
            print(f"Username set to: {i}")
            config["username"]["name"] = i
            break
        else:
            print("Invalid username.\n"
                  "Username must:\n"
                  "- Start with a lower-case letter.\n"
                  "- Be 1 to 32 characters.\n"
                  "- Only contain: a-z, 0-9, dash (-), or underscore (_).\n"
                  "- Not end with dash or underscore.\n"
                  "- Not be reserved (e.g., root, nobody...).\n")
            continue
    
    import getpass

    # User PW - Limitation: At least 6 chars if non-blank, max 64, can't contain spaces
    while True:
        i = getpass.getpass("Type in your password here for your user (Can be blank): ")
        if len(i) < 6:
            print("Password must be at least 6 characters, or blank if you do not want a password.")
            continue
        if len(i) > 64:
            print("Password must be 64 characters or fewer.")
            continue
        config["username"]["pw"] = i
        break

    # Root PW - Limitation: At least 8 chars, max 128, can't contain spaces, cannot be identical to username or blank
    while True:
        i = getpass.getpass("Type in the password for root (Password is recommended, use a PW you remember): ")
        if len(i) < 8:
            print("Password must be at least 8 characters.")
            continue
        if len(i) > 128:
            print("Password must be 128 characters or fewer.")
            continue
        if "name" in config["username"] and i == config["username"]["name"]:
            print("Root password shouldn't be identical to the username.")
            i=input("Continue? (y/n): ").lower().strip()
            if not i=="y":
                continue
        config["rootpw"] = i
        break

    # Desktop Environment (DE) and Browser selection

    # List of available DEs and their keys
    DEsList = {
        "Plasma": "plasma",
        "Gnome": "gnome"
    }

    # Mapping DE keys to package lists
    DEs = {
        "plasma": {
            "packages": "plasma kde-applications"
        },
        "gnome": {
            "packages": "gnome gnome-extra"
        }
    }

    # List of available browsers and their keys
    BrowsersList = {
        "Firefox": "firefox",
    }

    # Mapping browser keys to package lists
    Browsers = {
        "firefox": {"packages": "firefox"},
    }

    # Generalized selection logic for both DEs and Browsers
    def choose_option(options_dict, desc="option", allow_none=True):
        print(f"Choose a {desc}:")
        for idx, name in enumerate(options_dict.keys(), 1):
            print(f"{idx}: {name}")
        while True:
            try:
                choice = input(f"Enter the number for your desired {desc} (or leave blank for none): ").strip()
                if allow_none and choice == "":
                    print(f"No {desc} will be set.")
                    return None
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(options_dict):
                    key = list(options_dict.values())[choice_idx - 1]
                    print(f"Selected {desc}: {list(options_dict.keys())[choice_idx - 1]}")
                    return key
                else:
                    print("Invalid selection. Please try again.")
            except (ValueError, IndexError):
                print("Invalid input, please enter a valid number.")

    # Desktop Environment selection
    de_key = choose_option(DEsList, desc="desktop environment", allow_none=True)
    if de_key is not None:
        config["de"] = de_key
        config["de_packages"] = DEs[de_key]["packages"]
    else:
        config["de"] = None
        config["de_packages"] = ""

    # Browser selection (optional multiple select)
    print("Available browsers to install:")
    for idx, br_name in enumerate(BrowsersList.keys(), 1):
        print(f"{idx}: {br_name}")
    print("Select browsers by entering numbers separated by commas (e.g. 1,2). Leave blank for no browsers.")

    selected_browsers = []
    while True:
        choice = input("Your browser choice(s): ").strip()
        if choice == "":
            print("No browsers will be installed.")
            config["browsers"] = []
            break
        try:
            selections = [int(num) for num in choice.split(",") if num.strip()]
            valid = all(1 <= idx <= len(BrowsersList) for idx in selections)
            if not valid:
                print("Invalid selection(s). Please enter valid browser numbers.")
                continue
            br_keys = [list(BrowsersList.values())[idx-1] for idx in selections]
            config["browsers"] = br_keys
            # Also store flat list of packages to install for browsers
            config["browser_packages"] = [Browsers[k]["packages"] for k in br_keys]
            print("Selected browser(s):", ', '.join([list(BrowsersList.keys())[idx-1] for idx in selections]))
            break
        except Exception:
            print("Invalid input. Please enter numbers separated by commas (e.g. 1,2) or leave blank.")
            continue

    # Timezone selection with improved UX and input validation
    import re

    def is_valid_timezone(tz):
        # No slashes at start, no double slashes, valid chars, length limits, exists
        if not tz or tz.startswith('/') or '..' in tz or len(tz) > 64:
            return False
        if not re.match(r'^[A-Za-z0-9_\-\/]+$', tz):
            return False
        full_path = os.path.join('/usr/share/zoneinfo', tz)
        return os.path.isfile(full_path)

    while True:
        tz_input = input("Enter your timezone (Case-sensitive, e.g. Europe/London): ").strip()
        if not tz_input:
            print("Timezone cannot be empty. Please enter a valid timezone (e.g. Europe/London).")
            continue
        if not is_valid_timezone(tz_input):
            print("Invalid timezone format or timezone does not exist.")
            print("Examples: America/New_York, Europe/Paris, Asia/Tokyo")
            continue
        config["timezone"] = tz_input
        break

    # Language selection with more comprehensive validation & display, supporting complex locale names

    def is_valid_lang(lang, available_langs):
        # Accept anything present in /usr/share/i18n/locales as valid (including special cases)
        return lang in available_langs

    def fetch_langs():
        try:
            langs = os.listdir("/usr/share/i18n/locales")
            langs = [l.strip() for l in langs if l.strip()]
            langs.sort()
            return langs
        except Exception as e:
            print(f"Could not fetch locales automatically ({e}), please enter manually.")
            return []

    langs = fetch_langs()
    langs_upper = set(langs)
    while True:
        print("Type ? to show a paginated list of available locales.")
        i = input("Language/locale (see /usr/share/i18n/locales/ for all valid values, e.g. en_US, eu_ES@euro, iso14651_t1): ").strip()
        if i == "?":
            shown = 0
            per_page = 25
            total = len(langs)
            while shown < total:
                end_index = min(shown + per_page, total)
                print("Locales {}-{} of {}:".format(shown+1, end_index, total))
                print(", ".join(langs[shown:end_index]))
                shown = end_index
                if shown < total:
                    cont = input("-- Press Enter for next page or any character + Enter to stop -- ")
                    if cont.strip():
                        break
                else:
                    break
            continue
        elif i and is_valid_lang(i, langs_upper):
            config["lang"] = i
            print(f"Locale set to: {i}")
            break
        else:
            print("Invalid locale. It must exactly match one from /usr/share/i18n/locales/.")
            print("Examples: en_US, lt_LT, eu_ES@euro, iso14651_t1, translit_circle, ...")
            continue

    # Keymap selection with limitations & list support
    def fetch_keymaps():
        try:
            keymaps = subprocess.run(['localectl', '--no-pager','list-keymaps'], stdout=subprocess.PIPE, check=True, encoding='utf-8')
            return [k.strip() for k in keymaps.stdout.splitlines() if k.strip()]
        except Exception as e:
            print(f"Could not fetch keymaps automatically ({e}), please enter manually.")
            return []

    keymaps_list = fetch_keymaps()

    while True:
        print("\nKeymaps must be one of the available keymaps.")
        print("Examples: 'uk', 'lt', 'us', 'de', ...")
        print("Type '?' to view all available keymaps, or enter your selection:")

        i = input("Keymap: ").strip()
        if i == "?":
            # Paginate or print all available keymaps
            print("Available keymaps (first 25 shown):")
            print(", ".join(keymaps_list[:25]))
            if len(keymaps_list) > 25:
                print(f"... and {len(keymaps_list)-25} more not shown.")
            continue
        elif i and i in keymaps_list:
            config["keymap"] = i
            break
        else:
            print("Incorrect or unavailable keymap. Type '?' to list them. Example: uk, lt, us, de.")
            continue

    #Install

    extrapackages=f"{config["browser_packages"]} {config["de_packages"]} nano sudo gparted gnome-disk-utility git man"
    if config["boot_mode"]:
        extrapackages+=" grub efibootmgr"
    #Make swap image
    run_cmd(["sudo", "dd","if=/dev/zero","of=/target/swap.img","bs=1M",f"count={str(16*1024)}"])
    run_cmd(["sudo", "swapon","/target/swap.img"])

    #Update keyring and DBs so we don't have any download issues
    run_cmd(f"sudo pacman -Sy archlinux-keyring")

    #Install base system with extra packages
    run_cmd(f"sudo pacstrap -K /target base linux linux-firmware {extrapackages}".split(" "))

    #Setup fstab
    s=run_cmd(f"sudo genfstab -U /target".split(" "))
    with open("/target/etc/fstab") as file: file.write(s.stdout)

    def chroot_cmd(cmd,desc=""):
        """Command to run a command in chroot based off run_cmd(...)"""
        run_cmd(f"sudo arch-chroot /target {cmd}",desc)

    #Add timezone
    chroot_cmd(f"ln -sf /usr/share/zoneinfo/{config["timezone"]} /etc/localtime","Timezone symlink")
    chroot_cmd(f"hwclock --systohc", "Sync time")
    chroot_cmd(f"locale-gen", "Generate locales")
    run_cmd("sudo sh -c \"echo \"LANG="+config["locale"]+".UTF-8\nLC_ALL="+config["locale"]+".UTF-8\" >/target/etc/locale.conf\"","Lang, locale.conf")
    run_cmd("sudo sh -c \"echo \"KEYMAP="+config["keymap"]+"\">/target/etc/vconsole.conf\"","Keymap, vconsole.conf")

    #Add users
    chroot_cmd(f"useradd -m -G video,storage,wheel -s /bin/bash {config["username"]["name"]}", "Add user")

    #Setup paru and yay
    chroot_cmd(f"useradd -G video,storage,wheel -s /bin/bash tmpusr", "Add a temporary user")

    run_cmd("sudo mount --bind /tmp /target/tmp")
    chroot_cmd(f"mkdir /tmp/paru /tmp/yay")
    chroot_cmd(f"git clone https://aur.archlinux.org/paru.git /tmp/paru","Downloading AUR helper paru")
    chroot_cmd(f"bash -c \"cd /tmp/paru;sudo -u tmpusr makepkg -si\"","Building AUR helper paru")
    chroot_cmd(f"git clone https://aur.archlinux.org/yay.git /tmp/yay","Downloading AUR helper yay")
    chroot_cmd(f"bash -c \"cd /tmp/yay;sudo -u tmpusr makepkg -si\"","Building AUR helper yay")

    chroot_cmd(f"userdel tmpusr","Remove temporary user")

    if config["boot_mode"]=="uefi":
        chroot_cmd(f"grub-install --removable --bootloader-id=arch --efi-directory=/boot/efi","Running grub-install")#--removable so it may not get nuked by windows
        chroot_cmd(f"grub-mkconfig -o /boot/grub/grub.cfg","Running grub-mkconfig")
    else:
        print("NotImplemented")#TODO: Implement BIOS boot
    #Done, maybe: Forgotten step: Network setup
    #Think it is done: Select Disk: use gparted as a suitable partition editor, and maybe gnome disks, Partition Scheme: Automatic (recommended), Manual (launch cfdisk)
    #Think it is done: Filesystem: ext4 or btrfs
    #in config["boot_mode"] Boot mode detection (UEFI vs BIOS auto)
    #Done: Hostname
    #Done: User
    #Done: Root password
    #Done: DE selection
    #Done: Browser selection
    #Extras
    #Confirm
    #Check certain stuff, like if to install intel-ucode or amd-ucode
    #Install (live log)



    #config["username"]["pw"], config["username"]["name"], config["boot_mode"]. config["de"], config["de_packages"]
    # Save config for chroot stage
#    with open("/mnt/root/install_config.json", "w") as f:
#        json.dump(config, f, indent=4)

#    run_cmd(["arch-chroot", "/mnt", "python3", "/root/chroot_stage.py"], "Entering chroot stage")


def chroot_stage():
    """
    Runs inside chroot.
    Responsible for timezone, locale, users, DE, bootloader.
    """
    hprint("Starting chroot stage", "info", handler, "main")

    if not os.path.exists("/root/install_config.json"):
        hprint("Missing config file!", "critical", handler, "main")
        sys.exit(1)

    with open("/root/install_config.json") as f:
        config = json.load(f)

    # Example placeholder
    run_cmd(["ln", "-sf", "/usr/share/zoneinfo/UTC", "/etc/localtime"], "Setting timezone")

    hprint("Chroot stage complete", "info", handler, "main")


# -------- Main Entry --------

def main():
    global DBG, EXECUTE_COMMANDS

    hprint("Starting installer", "info", handler, "main")
    require_root()

    if "--debug" in sys.argv:
        DBG = True
        hprint("Debug mode enabled", "info", handler, "main")

        choice = input("1: Execute commands\n2: Dry-run\nChoose (1/2): ")
        EXECUTE_COMMANDS = (choice == "1")

    boot_mode = detect_boot_mode()

    # Example config structure (replace with Qt UI later)
    config = {
        "boot_mode": boot_mode,
    }

    # Detect if we're inside chroot or ISO
    if os.path.exists("/tmp/inside-archiso"): #File exists in archiso
        iso_stage(config)
    else:
        chroot_stage()

    hprint("Installer completed", "info", handler, "main")


if __name__ == "__main__":
    main()
