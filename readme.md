# Factorio As A Service

This python script has 2 major purposes: create easily a systemd service for factorio on Linux and 
updating the game automatically.

## Requirements

* Linux supporting systemd
* Sudo installed
* python >= 3.4
* git

## How to download it ?
Go to the desired directory for the installation and use this command:
```bash
git clone https://github.com/Pirheas/factorio_as_a_service.git
```

## How to use it ?

First, I recommend to create a new user who will own both this script and the whole game directory.

Use the `-v` flag for verbose. It may be useful for debugging

Type this command for help:
```bash
$ python3 ./faas.py -h
```

#### 1. Configuration file

Edit the configuration file (`config.ini`)


You will have to configure at least these fields:

* __factorio-path__ : Path of the factorio directory (it should contains a `bin` and a `data` directory)
* __save-path__ : Path of the saved game (zip file). If you don't have created it yet, consider reading [this tuto](https://wiki.factorio.com/Multiplayer#Dedicated.2FHeadless_server)
* __user__ : The user who will execute the factorio server (choose an existing linux user, `root` is a bad idea but will works)

By default the script will be looking for the file in: `/etc/faas/config.ini`. You need to create this folder manually:
```bash
sudo mkdir /etc/faas
cp ./config.ini /etc/faas/config.ini
```
If there is no file at `/etc/faas/config.ini` it will try to use the config file in the same directory `./config.ini`
Alternatively, you can run the command using the `-C` parameter to specify yourself the path of the config file:
```bash
python3 ./faas.py -C /home/me/myfaasconfig/config.ini -i
```

> NB: When you are using a relative path, the working directory will always be the directory that contains `faas.py`. Please consider using absolute path

#### 2. Download/Update the server

Once the destination is defined in the configuration file, execute the update command.
It will perform an update to the latest version (even if the directory is empty)

```bash
$ python3 ./faas.py -u
```

##### 2.1
If it's not done yet, [create your server save file](https://wiki.factorio.com/Multiplayer#Dedicated.2FHeadless_server)
and specify its path in `config.ini`

> Be sure that the user who is configured to launch the server has all permissions needed.
> Ex: Execute the binary, write in the save file, ...

#### 3. Create the Factorio Service
Simply run this command as __root__ 

```bash
# python3 ./faas.py -c
```

> If you change your configuration file, run this command to apply the modifications to the service

##### 3.1 Verify and control your service

Check the status of your service via:

```bash
$ systemctl status factorio
```

Start and stop the server with:

```bash
$ sudo systemctl start factorio
$ sudo systemctl stop factorio
```

#### 4 Automatic updates with cron

The script has been specially designed to be easily usable with crontab. Once you are sure everyting is OOK (service is up and running),
you can create new cron to automate the update.

Use this command to open the list of crontab (warning, execute it as the right user):

```bash
crontab -e
```

If you want to (checking) update every night, you can do add this line:

```bash
30 6 * * *   /path/to/faas.py -u
```

If you want it every hours with logs:

```bash
0 * * * *   /path/to/faas.py -u >> /path/to/logs.txt 2>&1
```

Validate and you're done.

> The execution of the cron will not stop your server if there is no update.
> If an update is applied, the server will be stopped during the installation and directly restarted after. 


## FAQ

#### What does this tool exactly ?
Basically, it has two goals: updating the server and create a systemd service to launch the server process.

The update server command can easily be configured with a cron. This way, it can be updated automatically.

#### Other tools already exist, why create a new one ?
None allow to both update and configure the server as a (systemd) service.
Plus this tool **automate a lot of things** and require a **minimum configuration** (3 fields only).
Last but no least, with the verbose option, the problems are really well explained and it's easy to find
what's wrong in case of failure

#### Do I need to stop the server before starting the update command ?
No, the update command will stop the server itself only if a new version is available. It will also restart 
the serve once the update is complete.

#### It doesn't work
Hey, that's not a question! Most likely, it's a file permission problem. Be sure the user configured to be owner of the process 
has the right to write and execute files in factorio directory.

In order to avoid permission issues, I advice you to create a `factorio` user (whatever the name) that will:
* Own the game directory
* Own `factorio_as_a_service` directory
* Be responsible of the crontab
* Be the owner of the server process (field `user` in `config.ini`)
* Always execute `faas.py` with this user (except when using -c flag since it requires root)

#### While extracting data during an update, I encounter an 'Operation not permitted'. What's the problem ?
Once again, it's a permission problem. Be sure to have the write permission on all factorio files. If not, use a `chmod -R`
to be sure the desired user is the owner of factorio directory.  

#### Are my saved game safe ?
Normally yes. Updates should not delete your saved games. But it's always safer to have backups.

#### Can I revert to a previous version ?
Not yet. You can do it manually and still run the service creation command though.

#### I used to specify the port as a parameter. It's not possible anymore. How do I do ?
Indeed, you must now specify parameters (such as the port) in the file `(Game directory)/config/config.ini`


#### I have multiple factorio servers running on my server. Can I still do that ?

Yes, but you'll need 2 different game install and 2 times factorio_as_a_service (one for each installed game).
You must also change the`service-name` for at least one of the faas.py in its `config.ini` file
