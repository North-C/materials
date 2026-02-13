# bpftrace 使用


## Ubuntu22.04上的小问题

问题：
```bash
root@test-ThinkCentre-M920t-N000:/home/test/lyq# bpftrace -e 'BEGIN { printf("hello world!\n"); }'
Attaching 1 probe...
ERROR: Could not resolve symbol: /proc/self/exe:BEGIN_trigger
```

解决办法：
```bash
sudo apt install ubuntu-dbgsym-keyring

echo "deb http://ddebs.ubuntu.com $(lsb_release -cs) main restricted universe multiverse
deb http://ddebs.ubuntu.com $(lsb_release -cs)-updates main restricted universe multiverse
deb http://ddebs.ubuntu.com $(lsb_release -cs)-proposed main restricted universe multiverse" | \
sudo tee -a /etc/apt/sources.list.d/ddebs.list

sudo apt install bpftrace-dbgsym
```

