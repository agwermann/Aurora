import json
import logging
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.validators import EMPTY_VALUES
from django.core.exceptions import ValidationError
from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response, redirect
from django.template import Context, RequestContext
from django.template.loader import get_template
from cloud.helpers import session_flash, paginate
from cloud.models.virtual_router import VirtualRouter, ROUTING_PROTOCOLS, CP_TYPES
from cloud.models.host import Host
from cloud.models.slice import Slice
from cloud.widgets.number_input import NumberInput
from cloud.models.remote_controller import CONNECTION_TYPES,\
    CONTROLLER_TYPE, RemoteController
from cloud.models.virtual_interface import VirtualInterface
from cloud.models.virtual_device import VirtualDevice
from cloud.models.virtual_link import VirtualLink

# Configure logging for the module name
logger = logging.getLogger(__name__)
view_vars = {
    'active_item': None,
    'active_menu': 'Network',
    'active_section': 'Virtual Routers',
}

#Form index filters
class VirtualRoutersIndexFiltersForm(forms.Form):
    slices = Slice.objects.all()
    slice_choices = (("", "---------------"), (-1, "--Unbound Virtual Routers--"))
    for slc in slices:
        slice_choices += ((slc.id, slc.name),)
    
    s = forms.ChoiceField(choices=slice_choices, label="Slice", required=False)

@login_required
def index(request):
    global view_vars
    form = VirtualRoutersIndexFiltersForm(request.GET) # Filter form
    if form.is_valid():
        s = form.cleaned_data['s']
        if s != '':
            # Search for unbound Virtual Routers
            if s == '-1':
                s = None
            vrs = VirtualRouter.objects.filter(belongs_to_slice=s)
        else:
            vrs = VirtualRouter.objects.all()
    else:
        vrs = []
    
    vr_list = paginate.paginate(vrs, request)

    t = get_template('virtual-routers-index.html')
    view_vars.update({
        'active_item': None,
        'title': 'Virtual Routers List',
        'actions': [{
            'name': 'New Virtual Router',
            'url': '/Aurora/cloud/virtual_routers/new/',
            'image': 'plus'
        }]
    })
    
    c = Context({
        'view_vars': view_vars,
        'vr_list': vr_list,
        'paginate_list': vr_list,
        'filter_form': form,
        'request': request,
        'flash': session_flash.get_flash(request)
    })
    
    return HttpResponse(t.render(c))

@login_required
def detail(request, virtual_router_id):
    global view_vars
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404

    view_vars.update({
        'active_item': vr,
        'title': 'Virtual Router Details',
        'actions': [{
            'name': 'Back to List',
            'url': '/Aurora/cloud/virtual_routers/',
            'image': 'chevron-left'
        }]
    })
    if_list = vr.virtualinterface_set.all()
    ofc_list = vr.remotecontroller_set.all()
    
    return render_to_response('virtual-routers-detail.html', {'vr': vr, 'if_list': if_list, 'ofc_list': ofc_list, 'view_vars': view_vars, 'request': request, 'flash': session_flash.get_flash(request) })

#Form for new Virtual Router creation
class VirtualRouterForm(forms.Form):
    action = "/Aurora/cloud/virtual_routers/new/"
    name = forms.CharField(max_length=200)
    cp_routing_protocol = forms.ChoiceField(choices=ROUTING_PROTOCOLS, required=False)
    cp_type = forms.ChoiceField(choices=CP_TYPES, required=False)
    belongs_to_slice = forms.ModelChoiceField(queryset=Slice.objects.all(), required=False)
    host = forms.ModelChoiceField(queryset=Host.objects.all(), empty_label=None)

@login_required
def new(request):
    global view_vars
    if request.method == 'POST': # If the form has been submitted...
        form = VirtualRouterForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            # Process the data in form.cleaned_data
            
            vr = VirtualRouter()
            vr.name = form.cleaned_data['name']
            vr.belongs_to_slice = form.cleaned_data['belongs_to_slice']
            vr.host = form.cleaned_data['host']
            
            # Save Virtual Router to get an ID
            vr.save()
            
            try:
                # Creates disk and defines Virtual Router in libvirt
                vr.deploy()
                session_flash.set_flash(request, "New Virtual Router successfully created")
            except vr.VirtualRouterException as e:
                session_flash.set_flash(request, "Problems deploying Virtual Router: %s" % str(e), "danger")
            
            return redirect('cloud-virtual-routers-index') # Redirect after POST
    else:
        form = VirtualRouterForm() # An unbound form
    
    view_vars.update({
        'active_item': None,
        'title': 'New Virtual Router',
        'actions': [{
            'name': 'Back to List',
            'url': 'javascript: history.back()',
            'image': 'chevron-left'
        }]
    })
    c = RequestContext(request, {
        'form': form,
        'view_vars': view_vars,
        'request': request,
        'flash': session_flash.get_flash(request) 
    })
    return render_to_response('base-form.html', c)

#Form for Virtual Router migration
#class VirtualRouterMigrationForm(forms.Form):
#    host = forms.ModelChoiceField(queryset=Host.objects.all(), empty_label=None)
#
#@login_required
#def migrate(request, virtual_router_id):
#    try:
#        vr = VirtualRouter.objects.get(pk=virtual_router_id)
#    except VirtualRouter.DoesNotExist:
#        raise Http404
#
#    if request.method == 'POST': # If the form has been submitted...
#        form = VirtualRouterMigrationForm(request.POST) # A form bound to the POST data
#        if form.is_valid(): # All validation rules pass
#            # Process the data in form.cleaned_data
#            
#            # Migrate Virtual Router to new host
#            try:
#                # TODO: investigate other options in the migration operation in libvirt 
#                vr.migrate(form.cleaned_data['host'])
#
#                # Save Virtual Router with new host
#                vr.host = form.cleaned_data['host']
#                vr.save()
#                
#                session_flash.set_flash(request, "Virtual Router successfully migrated")
#            except vr.VirtualRouterException as e:
#                session_flash.set_flash(request, "Could not migrate Virtual Router %s: %s" % (vr.name, str(e)), "danger")
#                logger.warning("Could not migrate Virtual Router %s: %s" % (vr.name, str(e)))
#            
#            return redirect('cloud-virtual-routers-index') # Redirect after POST
#    else:
#        form = VirtualRouterMigrationForm() # An unbound form
#
#    
#    view_vars = {
#        'active_menu': active_menu,
#        'title': "Migrate Virtual Router",
#        'actions': [
#            { 'name': "Back to List", 'url': "javascript: history.back()" },
#        ]
#    }
#    c = RequestContext(request, {
#        'vr': vr,
#        'form': form,
#        'view_vars': view_vars,
#        'request': request,
#        'flash': session_flash.get_flash(request) 
#    })
#    return render_to_response('virtual-routers-migrate.html', c)

#Form for new Remote Controller creation
class RemoteControllerForm(forms.Form):
    action = "/Aurora/cloud/virtual_routers/%s/new_remote_controller/"
    belongs_to_slice = forms.ModelChoiceField(queryset=Slice.objects.all(), required=False)
    ip = forms.CharField(max_length=100)
    port = forms.IntegerField(widget=NumberInput(attrs={"max": 65536, "min": 1, "step": 1}), max_value=65536, min_value=1, help_text="default 6633")
    connection = forms.ChoiceField(choices=CONNECTION_TYPES)
    controller_type = forms.ChoiceField(choices=CONTROLLER_TYPE)
    
@login_required
def new_remote_controller(request, virtual_router_id):
    global view_vars
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404
    
    if request.method == 'POST': # If the form has been submitted...
        form = RemoteControllerForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            # Process the data in form.cleaned_data
            
            rc = RemoteController()
            rc.belongs_to_slice = form.cleaned_data['belongs_to_slice']
            rc.ip = form.cleaned_data['ip']
            rc.port = form.cleaned_data['port']
            rc.connection = form.cleaned_data['connection']
            rc.controller_type = form.cleaned_data['controller_type']
            rc.controls_vrouter = vr
            rc.save()
            
            try:
                # Redeploy router to set controller
                vr.deploy()
                session_flash.set_flash(request, "New Remote Controller successfully added")
            except vr.VirtualRouterException as e:
                session_flash.set_flash(request, "Problems adding Remote Controller: %s" % str(e), "danger")
            
            return redirect('/Aurora/cloud/virtual_routers/' + virtual_router_id + '/') # Redirect after POST
    else:
        form = RemoteControllerForm() # An unbound form
    
    view_vars.update({
        'active_item': vr,
        'title': 'New Remote Controller for ' + vr.name,
        'actions': [{
            'name': 'Back to Details',
            'url': '/Aurora/cloud/virtual_routers/' + virtual_router_id + '/',
            'image': 'chevron-left'
        }]
    })
    # insert slice_id in the action url
    form.action = form.action % virtual_router_id
    c = RequestContext(request, {
        'vr': vr,
        'form': form,
        'view_vars': view_vars,
        'request': request,
        'flash': session_flash.get_flash(request) 
    })
    return render_to_response('base-form.html', c)

@login_required
def delete_remote_controller(request, virtual_router_id, remote_controller_id):
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404

    try:
        rc = RemoteController.objects.get(pk=remote_controller_id, controls_vrouter=vr)
    except RemoteController.DoesNotExist:
        raise Http404

    # Keep name temporarily
    rc_name = str(rc)
    rc.delete()
    try:
        # Redeploy router to set controller
        vr.deploy()
        session_flash.set_flash(request, "Remote Controller %s was successfully deleted!" % rc_name)
        logger.debug("Remote Controller %s was successfully deleted!" % rc_name)
    except vr.VirtualRouterException as e:
        session_flash.set_flash(request, "Could not update controller list for %s: %s" % (vr.name, str(e)), "warning")
    
    return redirect(request.META['HTTP_REFERER'])

#Form for new Virtual Interface creation
class VirtualInterfaceForm(forms.Form):
    action = "/Aurora/cloud/virtual_routers/%s/new_virtual_interface/"
    alias = forms.CharField(max_length=20)
    
@login_required
def new_virtual_interface(request, virtual_router_id):
    global view_vars
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404
    
    if request.method == 'POST': # If the form has been submitted...
        form = VirtualInterfaceForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            # Process the data in form.cleaned_data
            
            interface = VirtualInterface()
            interface.alias = form.cleaned_data['alias']
            interface.mac_address = None
            interface.attached_to = vr
            interface.save()

            session_flash.set_flash(request, "New Virtual Interface successfully added")
            
            return redirect('/Aurora/cloud/virtual_routers/' + virtual_router_id + '/') # Redirect after POST
    else:
        form = VirtualInterfaceForm() # An unbound form
    
    view_vars.update({
        'active_item': vr,
        'title': 'New Virtual Interface for ' + vr.name,
        'actions': [{
            'name': 'Back to Details',
            'url': '/Aurora/cloud/virtual_routers/' + virtual_router_id + '/',
            'image': 'chevron-left'
        }]
    })
    # insert slice_id in the action url
    form.action = form.action % virtual_router_id
    c = RequestContext(request, {
        'vr': vr,
        'form': form,
        'view_vars': view_vars,
        'request': request,
        'flash': session_flash.get_flash(request) 
    })
    return render_to_response('base-form.html', c)

@login_required
def delete_virtual_interface(request, virtual_router_id, virtual_interface_id):
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404

    try:
        vi = VirtualInterface.objects.get(pk=virtual_interface_id, attached_to=vr)
    except VirtualInterface.DoesNotExist:
        raise Http404

    # Need to unestablish all virtual links associated with this interface
    for link in vi.connected_virtual_links():
        try:
            link.unestablish()
        except vr.VirtualLinkException as e:
            session_flash.set_flash(request, "Could not unestablish Virtual Link %s: %s" % (str(link), str(e)), "warning")
    
    # Keep name temporarily
    vi_name = str(vi)
    vi.delete()
    session_flash.set_flash(request, "Virtual Interface %s was successfully deleted!" % vi_name)
    logger.debug("Virtual Interface %s was successfully deleted!" % vi_name)
    return redirect(request.META['HTTP_REFERER'])


@login_required
def delete(request, virtual_router_id):
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404

    try:
        vr.undeploy()
        session_flash.set_flash(request, "Virtual Router %s was successfully deleted!" % vr.name)
        logger.debug("Virtual Router %s was successfully deleted!" % vr.name)
    except vr.VirtualRouterException as e:
        session_flash.set_flash(request, "Could not undefine Virtual Router on hypervisor %s: %s" % (vr.name, str(e)), "warning")
        logger.warning("Could not undefine Virtual Router on hypervisor %s: %s" % (vr.name, str(e)))
    
    # Delete VM from database anyway
    vr.delete()
    
    return redirect(request.META['HTTP_REFERER'])

# Webservice to get interface details for a Virtual Router
@login_required
def interfaces(request, virtual_router_id):
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
    except VirtualRouter.DoesNotExist:
        raise Http404

    if_list = vr.get_interface_info()
    
    output = []
    for interface in if_list:
        output.append([
            interface.id,
            "Interface " + str( interface.alias ) + " - " + interface.mac_address
        ])
    
    # Output format is [ [mac1, label1], [mac2, label2], ... [macN, labelN]] 
    return HttpResponse(json.dumps(output), mimetype='application/json')

class VirtualDeviceModelChoiceField(forms.ModelChoiceField):
    # Override to_python function to avoid "select a valid choice" errors
    def to_python(self, value):
        if value in EMPTY_VALUES:
            return None
        try:
            dev = VirtualDevice.objects.get(pk=value)
        except VirtualDevice.DoesNotExist:
            raise ValidationError(self.error_messages['invalid_choice'])
        return dev

class VirtualInterfaceModelChoiceField(forms.ModelChoiceField):
    # Override to_python function to avoid "select a valid choice" errors
    def to_python(self, value):
        if value in EMPTY_VALUES:
            return None 
        try:
            interface = VirtualInterface.objects.get(pk=value)
        except VirtualInterface.DoesNotExist:
            raise ValidationError(self.error_messages['invalid_choice'])
        return interface

#Form for connecting devices to ports
class ConnectVirtualDeviceForm(forms.Form):
    virtual_device_type = forms.ChoiceField(
        choices=(("virtual_routers", "Virtual Routers"), ("virtual_machines", "Virtual Machines")),
        widget=forms.RadioSelect(attrs={'onChange':'select_load_options(this, "/Aurora/cloud/virtual_devices/__selected_id__/", "id_virtual_device")'})
    )
    virtual_device = VirtualDeviceModelChoiceField(
        queryset=VirtualDevice.objects.none(),
        widget=forms.Select(attrs={'onChange':'select_load_options(this, "/Aurora/cloud/virtual_devices/__selected_id__/virtual_interfaces/", "id_virtual_interface")'})
    )
    virtual_interface = VirtualInterfaceModelChoiceField(queryset=VirtualInterface.objects.none(), label="Interface")
    
def connect_virtual_device(request, virtual_router_id, virtual_interface_id):
    global view_vars
    try:
        vr = VirtualRouter.objects.get(pk=virtual_router_id)
        interface = VirtualInterface.objects.get(pk=virtual_interface_id, attached_to=vr)
    except VirtualRouter.DoesNotExist:
        raise Http404
    
    if request.method == 'POST': # If the form has been submitted...
        form = ConnectVirtualDeviceForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            # Process the data in form.cleaned_data
            
            virtual_interface = form.cleaned_data['virtual_interface']
            
            virtual_link = VirtualLink()
            virtual_link.belongs_to_slice = vr.belongs_to_slice # Same slice as the router
            virtual_link.if_start = interface
            virtual_link.if_end = virtual_interface
            
            virtual_link.save()
            try:
                virtual_link.establish()
                session_flash.set_flash(request, "Virtual Device successfully connected")
            except virtual_link.VirtualLinkException as e:
                session_flash.set_flash(request,
                    "Could not establish Virtual Link %s: %s" % (str(virtual_link), str(e)),
                    "danger"
                )
            
            return redirect('/Aurora/cloud/virtual_routers/' + virtual_router_id + '/') # Redirect after POST
    else:
        form = ConnectVirtualDeviceForm() # An unbound form
    
    view_vars.update({
        'active_item': vr,
        'title': 'Connect Virtual Device on interface ' + interface.alias + ' of ' + vr.name,
        'actions': [{
            'name': 'Back to Details',
            'url': '/Aurora/cloud/virtual_routers/' + virtual_router_id + '/',
            'image': 'chevron-left'
        }]
    })
    c = RequestContext(request, {
        'virtual_router': vr,
        'virtual_interface': interface,
        'form': form,
        'view_vars': view_vars,
        'request': request,
        'flash': session_flash.get_flash(request) 
    })
    return render_to_response('base-form.html', c)

