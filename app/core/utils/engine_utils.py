"""Engine lifecycle utilities - timing"""

import logging

logger = logging.getLogger(__name__)


def log_timing_report(timing_dict: dict):
    """Log execution timing report"""
    if not timing_dict:
        return
    
    logger.info("="*60)
    logger.info("⏱️  EXECUTION TIMING REPORT")
    logger.info("="*60)
    
    total = sum(timing_dict.values())
    
    for node, elapsed in sorted(timing_dict.items(), key=lambda x: x[1], reverse=True):
        percentage = (elapsed / total * 100) if total > 0 else 0
        logger.info(f"  {node:.<30} {elapsed:>8.1f}ms ({percentage:>5.1f}%)")
    
    logger.info("-"*60)
    logger.info(f"  {'TOTAL':.<30} {total:>8.1f}ms (100.0%)")
    logger.info("="*60)
