import asyncio
import logging
from typing import Any, List, Dict


class MultiOutputInterface:
    """Wrapper for multiple output interfaces to write data to all outputs simultaneously."""

    def __init__(self, interfaces: List[Any]):
        self.interfaces = interfaces
        self.is_running = False

    async def initialize(self) -> bool:
        """Initialize all output interfaces."""
        try:
            # Initialize all interfaces concurrently
            results = await asyncio.gather(
                *[interface.initialize() for interface in self.interfaces],
                return_exceptions=True
            )
            
            # Check if any initialization failed
            failed_interfaces = []
            for idx, result in enumerate(results):
                if isinstance(result, Exception) or result is False:
                    failed_interfaces.append(idx)
                    logging.error(f"Output interface {idx} failed to initialize: {result}")

            # Consider initialization successful if at least one interface works
            successful_interfaces = len(self.interfaces) - len(failed_interfaces)
            if successful_interfaces == 0:
                logging.error("All output interfaces failed to initialize")
                return False

            if failed_interfaces:
                logging.warning(f"{len(failed_interfaces)} output interface(s) failed, "
                               f"continuing with {successful_interfaces} working interface(s)")
                # Remove failed interfaces from the list
                self.interfaces = [self.interfaces[i] for i in range(len(self.interfaces)) 
                                 if i not in failed_interfaces]

            self.is_running = True
            logging.info(f"MultiOutputInterface initialized successfully with {len(self.interfaces)} interface(s)")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize MultiOutputInterface: {e}")
            return False

    async def write_data(self, results: Dict[str, Any]) -> bool:
        """Write data to all output interfaces concurrently."""
        if not self.is_running:
            raise RuntimeError("MultiOutputInterface not initialized")

        try:
            # Write to all interfaces concurrently
            write_tasks = []
            for idx, interface in enumerate(self.interfaces):
                try:
                    task = interface.write_data(results)
                    write_tasks.append(task)
                except Exception as e:
                    logging.error(f"Error creating write task for interface {idx}: {e}")

            if not write_tasks:
                logging.warning("No write tasks created")
                return False

            # Wait for all writes to complete
            write_results = await asyncio.gather(*write_tasks, return_exceptions=True)

            # Check results
            successful_writes = 0
            for idx, result in enumerate(write_results):
                if isinstance(result, Exception):
                    logging.error(f"Write failed for output interface {idx}: {result}")
                elif result is True:
                    successful_writes += 1
                else:
                    logging.warning(f"Write returned non-True result for interface {idx}: {result}")

            # Consider success if at least one write succeeded
            success = successful_writes > 0
            if not success:
                logging.error("All output writes failed")
            elif successful_writes < len(write_tasks):
                logging.warning(f"Only {successful_writes}/{len(write_tasks)} outputs succeeded")

            return success

        except Exception as e:
            logging.error(f"Error in MultiOutputInterface write_data: {e}")
            return False

    async def cleanup(self):
        """Clean up all output interfaces."""
        self.is_running = False

        if not self.interfaces:
            logging.info("No interfaces to cleanup")
            return

        try:
            # Cleanup all interfaces concurrently
            cleanup_tasks = []
            for interface in self.interfaces:
                try:
                    task = interface.cleanup()
                    cleanup_tasks.append(task)
                except Exception as e:
                    logging.error(f"Error creating cleanup task for interface: {e}")

            if cleanup_tasks:
                cleanup_results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                
                for idx, result in enumerate(cleanup_results):
                    if isinstance(result, Exception):
                        logging.error(f"Cleanup failed for output interface {idx}: {result}")

        except Exception as e:
            logging.error(f"Error during MultiOutputInterface cleanup: {e}")

        logging.info("MultiOutputInterface cleaned up")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all output interfaces."""
        status = {
            'is_running': self.is_running,
            'interface_count': len(self.interfaces),
            'interfaces': []
        }

        for idx, interface in enumerate(self.interfaces):
            interface_info = {
                'index': idx,
                'type': type(interface).__name__,
                'is_running': getattr(interface, 'is_running', 'unknown')
            }

            # Add specific info based on interface type
            if hasattr(interface, 'output_path'):
                interface_info['output_path'] = interface.output_path
            if hasattr(interface, 'addr'):
                interface_info['addr'] = interface.addr
            if hasattr(interface, 'topic'):
                interface_info['topic'] = interface.topic

            status['interfaces'].append(interface_info)

        return status 