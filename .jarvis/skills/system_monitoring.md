# System Monitoring with psutil

Monitor system resources including CPU, GPU, memory, disk usage, and running processes.

## Code

```python
import psutil
import subprocess
import shutil

def get_system_info():
    """
    Get comprehensive system information including GPU metrics.
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

    # GPU
    gpu_info = []
    
    # Check if nvidia-smi exists before trying to run it
    if shutil.which('nvidia-smi') is None:
        gpu_info = ["GPU: nvidia-smi not found (Drivers might be missing)"]
    else:
        try:
            # Query GPU data
            output = subprocess.check_output(
                ['nvidia-smi', '--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv'],
                stderr=subprocess.STDOUT
            ).decode()
            
            lines = output.strip().split('\n')
            
            # THE FIX: Strip whitespace from headers to avoid KeyError: ' index'
            headers = [h.strip() for h in lines[0].split(',')]
            
            for line in lines[1:]:
                # THE FIX: Strip whitespace from values too
                values = [v.strip() for v in line.split(',')]
                gpu_data = {h: v for h, v in zip(headers, values)}
                
                gpu_info.append(
                    f"GPU {gpu_data.get('index', '?')}: {gpu_data.get('name', 'Unknown')} | "
                    f"Temp: {gpu_data.get('temperature.gpu', 'N/A')}°C | "
                    f"Load: {gpu_data.get('utilization.gpu', '0%')} | "
                    f"VRAM: {gpu_data.get('memory.used', '0')} / {gpu_data.get('memory.total', '0')}"
                )
        except subprocess.CalledProcessError:
            gpu_info = ["GPU: nvidia-smi failed to run (Driver/Kernel mismatch?)"]
        except Exception as e:
            gpu_info = [f"GPU Error: {str(e)}"]

    return f"""System Status:
----------------
CPU:    {cpu_percent}% ({cpu_count} cores)
Memory: {mem_used_gb:.1f}GB / {mem_total_gb:.1f}GB ({mem_percent}%)
Disk:   {disk_used_gb:.1f}GB / {disk_total_gb:.1f}GB ({disk_percent}%)
----------------
{chr(10).join(gpu_info)}
"""

if __name__ == "__main__":
    print(get_system_info())
```

## Usage Examples

- Check system resource usage
- Monitor CPU and memory
- Check disk space availability
- Monitor GPU utilisation and total memory
