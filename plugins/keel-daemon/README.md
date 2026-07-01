# keel-daemon

Long-running background daemon SDK for keel plugins.

## Installation

```bash
pip install keel-daemon
```

## Usage

Create a custom daemon by subclassing `KeelingDaemon`:

```python
from keel_daemon.daemon import KeelingDaemon

class MyDaemon(KeelingDaemon):
    id = "my-daemon"
    interval = 10  # seconds
    
    def on_start(self) -> None:
        # Called when daemon starts
        pass
    
    def on_tick(self) -> None:
        # Called periodically
        pass
    
    def on_stop(self) -> None:
        # Called when daemon stops
        pass

if __name__ == "__main__":
    daemon = MyDaemon()
    daemon.run()
```
