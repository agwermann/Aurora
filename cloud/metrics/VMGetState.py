# This is only a test file
import logging
from cloud.metrics.metric import Metric
from cloud.models.virtual_machine import VirtualMachine

# Configure logging for the module name
logger = logging.getLogger(__name__)

# Extends the Metric class to inherit basic functionalities
class VMGetState(Metric):

    # Implementation of deployment method
    def collect(self, vm_name=None):
        try:
            vm = VirtualMachine.objects.get(name=vm_name)
            return vm.current_state()
        except VirtualMachine.DoesNotExist:
            raise self.MetricException('No VM with name %s' % vm_name)
        except VirtualMachine.VirtualMachineException as e:
            raise self.MetricException('Error: %s' % str(e))