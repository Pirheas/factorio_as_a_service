# Factorio As A Service

Python script that allows to create a Factorio service on systemd.
It also allows to (auto)update the game to the latest version.
With a cron you can even automate this task.

## Requirements

* Linux supporting systemd
* python >= 3.4

## How to use it ?

First, use this command to show help:
Use the `-v` flag for verbose. It may be useful for debugging


```bash
$ python3 ./faas.py -h
```

#### 1. Configuration file

Edit the configuration file (`config.ini`)


You will have to configure at least these fields:

* __factorio-path__ : Path of the factorio directory (it should contains a `bin` and a `data` directory)
* __save-path__ : Path of the saved game (zip file). If you don't have created it yet, consider reading [this tuto](https://wiki.factorio.com/Multiplayer#Dedicated.2FHeadless_server)
* __user__ : The user who will execute the factorio server (choose an existing linux user, `root` is a bad idea but will works)

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

*Documentation TODO*

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


#### Are my saved game safe ?
Normally yes. Updates should not delete your saved games. But it's always safer to have backups.

#### Can I revert to a previous version ?
Not yet. You can do it manually and still run the service creation command though.


