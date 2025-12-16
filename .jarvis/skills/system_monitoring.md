# System Monitoring with psutil

Monitor system resources including CPU, memory, disk usage, and running processes.

## Code

```python
import psutil

def get_system_info():
    """
    Get comprehensive system information.
    """
    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    
    # Memory
    mem = psutil.virtual_memory()
    mem_total_gb = mem.total / (1024**3)
    mem_used_gb = mem.used / (1024**3)
    mem_percent = mem.percent
    
    # Disk
    disk = psutil.disk_usage('/')
    disk_total_gb = disk.total / (1024**3)
    disk_used_gb = disk.used / (1024**3)
    disk_percent = disk.percent
    
    return f"""System Status:
CPU: {cpu_percent}% ({cpu_count} cores)
Memory: {mem_used_gb:.1f}GB / {mem_total_gb:.1f}GB ({mem_percent}%)
Disk: {disk_used_gb:.1f}GB / {disk_total_gb:.1f}GB ({disk_percent}%)
"""

print(get_system_info())
```

## Usage Examples

- Check system resource usage
- Monitor CPU and memory
- Check disk space availability
