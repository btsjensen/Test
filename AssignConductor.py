import cympy


def check_default_cond(cond_id, default_ids):
    """
    Checks if conductor ID is a default conductor
    :param cond_id: Conductor ID string
    :param default_ids: Default conductor IDs list
    :return: Bool indicating if conductor ID is valid or default
    """
    default_bool = False
    for default_id in default_ids:
        if default_id in cond_id:
            default_bool = True
            break

    return default_bool


def get_conductors(ckt_name, cond_defaults):
    """
    Gets dictionary of overhead line, overhead line by phase, overhead line unbalanced, and underground conductors
    Key: section ID, value: conductor device object
    :param ckt_name: String of circuit name
    :param cond_defaults: List of default conductor IDs
    :return: Dictionary of conductor devices, list of OH and OH unbalanced conductors, list of OH by phase conductors,
    list of UG cables
    """
    # Initialize dictionary of conductors, lists of default conductors
    cond_dict = {}
    oh_default_list = []
    oh_phase_default_list = []
    oh_unbalanced_default_list = []
    ug_cable_default_list = []

    # Get list of all devices
    oh_cond_list = cympy.study.ListDevices(cympy.enums.DeviceType.OverheadLine, ckt_name)
    oh_phase_cond_list = cympy.study.ListDevices(cympy.enums.DeviceType.OverheadByPhase, ckt_name)
    oh_unbalanced_cond_list = cympy.study.ListDevices(cympy.enums.DeviceType.OverheadLineUnbalanced, ckt_name)
    ug_cable_list = cympy.study.ListDevices(cympy.enums.DeviceType.Underground, ckt_name)

    # Iterate through all overhead lines,
    # add to dictionary, remove if section has other conductor (in dictionary) or not default
    for oh_cond in oh_cond_list:
        if oh_cond.SectionID not in cond_dict:
            cond_dict[oh_cond.SectionID] = oh_cond
            if check_default_cond(oh_cond.GetValue('LineID'), cond_defaults):
                oh_default_list.append(oh_cond)
    # Iterate through all overhead lines by phase,
    # add to dictionary, remove if section has other conductor (in dictionary) or not default
    for oh_phase_cond in oh_phase_cond_list:
        if oh_phase_cond.SectionID not in cond_dict:
            cond_dict[oh_phase_cond.SectionID] = oh_phase_cond
            if check_default_cond(oh_phase_cond.GetValue('PhaseConductorIDA'), cond_defaults) or \
                    check_default_cond(oh_phase_cond.GetValue('PhaseConductorIDB'), cond_defaults) or \
                    check_default_cond(oh_phase_cond.GetValue('PhaseConductorIDC'), cond_defaults) or \
                    check_default_cond(oh_phase_cond.GetValue('NeutralConductorID1'), cond_defaults) or \
                    check_default_cond(oh_phase_cond.GetValue('NeutralConductorID2'), cond_defaults):
                oh_phase_default_list.append(oh_phase_cond)
    # Iterate through all overhead lines unbalanced,
    # add to dictionary, remove if section has other conductor (in dictionary) or not default
    for oh_unbalanced_cond in oh_unbalanced_cond_list:
        if oh_unbalanced_cond.SectionID not in cond_dict:
            cond_dict[oh_unbalanced_cond.SectionID] = oh_unbalanced_cond
            if check_default_cond(oh_unbalanced_cond.GetValue('LineID'), cond_defaults):
                oh_unbalanced_default_list.append(oh_unbalanced_cond)
    # Iterate through all underground cables,
    # add to dictionary, remove if section has other conductor (in dictionary) or not default
    for ug_cable in ug_cable_list:
        if ug_cable.SectionID not in cond_dict:
            cond_dict[ug_cable.SectionID] = ug_cable
            if check_default_cond(ug_cable.GetValue('CableID'), cond_defaults):
                ug_cable_default_list.append(ug_cable)

    return cond_dict, oh_default_list + oh_unbalanced_default_list, oh_phase_default_list, ug_cable_default_list


def get_cond(old_cond, up_dw, conductor_dict, line_id_names, depth_max, kva_diff_max, default_cond_ids):
    """
    Looks for upstream/downstream conductor, if conductor within kVA difference max
    :param old_cond: Default conductor object
    :param up_dw: Up or down string
    :param conductor_dict: Conductor dictionary with section ID as key, conductor as object
    :param line_id_names: conductor type get value list of strings
        ('LineID'/'PhaseConductorIDA'/'PhaseConductorIDB'/'PhaseConductorIDC'/'CableID')
    :param depth_max: Max depth before breaking (how far upstream does script check)
    :param kva_diff_max: kVA difference that want to stay between
    :param default_cond_ids: default conductor IDs list
    :return: Upstream/downstream conductor string and boolean with if upstream conductor within kVA difference max
    """
    # Get section, downstream kVA of default conductor
    sect = cympy.study.GetSection(old_cond.SectionID)
    sect_dw_kva = float(cympy.study.QueryInfoDevice('DwKVAT', old_cond.DeviceNumber, old_cond.DeviceType))

    # Initialize new conductor dictionary, bool if within kVA
    new_cond = {}
    for line_id_name in line_id_names:
        new_cond[line_id_name] = 'N/A'
    in_kva = False

    # Create iterator
    if up_dw == 'UP':
        it = cympy.study.NetworkIterator(sect.FromNode.ID, cympy.enums.IterationOption.Upstream)
    else:
        it = cympy.study.NetworkIterator(sect.ToNode.ID, cympy.enums.IterationOption.Downstream)

    # Iterate upstream/downstream
    while it.Next():
        # If section is default section then increment max depth (don't count default section) and continue
        if it.GetSection() == sect:
            depth_max += 1
            continue

        # Check if more than depth_max sections upstream/downstream,
        # If so then exit (if going up) or continue (if going down)
        if it.GetDepth() > depth_max:
            if up_dw == 'UP':
                break
            else:
                continue

        in_kva = False

        # Check if section in conductor dictionary
        if it.GetSection().ID in conductor_dict:
            # If conductor type is different than default conductor then break
            if conductor_dict[it.GetSection().ID].DeviceType != old_cond.DeviceType:
                break

            # Check if downstream kVA within kva_diff_max
            if (sect_dw_kva != 0) and \
                    (abs(float(cympy.study.QueryInfoDevice('DwKVAT', conductor_dict[it.GetSection().ID].DeviceNumber,
                                                           conductor_dict[it.GetSection().ID].DeviceType)) -
                         sect_dw_kva) / sect_dw_kva < kva_diff_max):
                in_kva = True

            # Loop through line IDs
            sect_conductors = new_cond.copy()
            next_cond = False
            good_line_ids = []
            for line_id_name in line_id_names:
                # If iterator conductor is not default, then try to get conductor, else continue
                if not check_default_cond(conductor_dict[it.GetSection().ID].GetValue(line_id_name), default_cond_ids):
                    # If not set then set upstream/downstream conductor
                    if sect_conductors[line_id_name] == 'N/A':
                        sect_conductors[line_id_name] = conductor_dict[it.GetSection().ID].GetValue(line_id_name)
                    # Else if set but same as before then no action
                    elif sect_conductors[line_id_name] == conductor_dict[it.GetSection().ID].GetValue(line_id_name):
                        pass
                    # Else if different than conductor before then set equal to 'CA' (can't assign)
                    elif sect_conductors[line_id_name] != conductor_dict[it.GetSection().ID].GetValue(line_id_name):
                        sect_conductors[line_id_name] = 'CA'

                    # If got conductor and within kVA range, or 'CA' then mark line ID as good (append 0),
                    # else bad (append 1)
                    if ((sect_conductors[line_id_name] != 'N/A') and in_kva) or (sect_conductors[line_id_name] == 'CA'):
                        good_line_ids.append(0)
                    else:
                        good_line_ids.append(1)
                else:
                    next_cond = True
                    break

            if next_cond:
                continue

            new_cond = sect_conductors.copy()
            del sect_conductors

            # If got all good line IDs or got 'CA' (only appended 0s to good_line_ids) then break
            if sum(good_line_ids) == 0:
                break

    # If didn't assign conductor then set equal to 'CA' (no good conductors in range)
    for line_id_name in line_id_names:
        if new_cond[line_id_name] == 'N/A':
            new_cond[line_id_name] = 'CA'

    return new_cond, in_kva


def assign_cond(assign_conductor, line_type_ids, cond_dictionary, changed_dict, ir_dict,
                it_depth_max, kva_pct_max, default_list):
    """
    Assigns conductor IDs
    :param assign_conductor: conductor object
    :param line_type_ids: line type ID string
    :param cond_dictionary: conductor dictionary
    :param changed_dict: changed dictionary
    :param ir_dict: input required dictionary
    :param it_depth_max: max iterations upstream/downstream
    :param kva_pct_max: max percent difference in kVA
    :param default_list: default conductor list
    :return: changed dictionary, input required dictionary
    """
    # Get upstream conductor, within kVA bool
    up_cond, up_kva = get_cond(assign_conductor, 'UP', cond_dictionary, line_type_ids,
                               it_depth_max, kva_pct_max, default_list)

    # Get downstream conductor, within kVA bool
    down_cond, down_kva = get_cond(assign_conductor, 'DOWN', cond_dictionary, line_type_ids,
                                   it_depth_max, kva_pct_max, default_list)

    for line_type_id in line_type_ids:
        # Initialize output dictionary
        changed_cond_dict = {'SECTION': '', 'OLD': '', 'NEW': '', 'LINEID': line_type_id}
        ir_cond_dict = {'SECTION': '', 'UPSTREAM': '', 'DOWNSTREAM': '', 'LINEID': line_type_id,
                        'COND': assign_conductor}

        # If upstream conductor is not 'CA' but downstream is 'CA', use upstream
        if (up_cond[line_type_id] != 'CA') and (down_cond[line_type_id] == 'CA'):
            changed_cond_dict['SECTION'] = assign_conductor.SectionID
            changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
            changed_cond_dict['NEW'] = up_cond[line_type_id]
            changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
            assign_conductor.SetValue(up_cond[line_type_id], line_type_id)

        # Else if upstream conductor is 'CA' but downstream is not 'CA', use downstream
        elif (up_cond[line_type_id] == 'CA') and (down_cond[line_type_id] != 'CA'):
            changed_cond_dict['SECTION'] = assign_conductor.SectionID
            changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
            changed_cond_dict['NEW'] = down_cond[line_type_id]
            changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
            assign_conductor.SetValue(down_cond[line_type_id], line_type_id)

        # Else if both are 'CA' then input required
        elif (up_cond[line_type_id] == 'CA') and (down_cond[line_type_id] == 'CA'):
            ir_cond_dict['SECTION'] = assign_conductor.SectionID
            ir_cond_dict['UPSTREAM'] = up_cond[line_type_id]
            ir_cond_dict['DOWNSTREAM'] = down_cond[line_type_id]
            ir_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = ir_cond_dict.copy()

        # Else if both are not 'CA'
        else:
            # If both same, then use downstream
            if up_cond[line_type_id] == down_cond[line_type_id]:
                changed_cond_dict['SECTION'] = assign_conductor.SectionID
                changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
                changed_cond_dict['NEW'] = down_cond[line_type_id]
                changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
                assign_conductor.SetValue(down_cond[line_type_id], line_type_id)
            # Else (upstream, downstream different)
            else:
                # If upstream within kVA and downstream not within kVA then, use upstream
                if up_kva and not down_kva:
                    changed_cond_dict['SECTION'] = assign_conductor.SectionID
                    changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
                    changed_cond_dict['NEW'] = up_cond[line_type_id]
                    changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
                    assign_conductor.SetValue(up_cond[line_type_id], line_type_id)
                # Else if upstream not within kVA and downstream within kVA, then use downstream
                elif not up_kva and down_kva:
                    changed_cond_dict['SECTION'] = assign_conductor.SectionID
                    changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
                    changed_cond_dict['NEW'] = down_cond[line_type_id]
                    changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
                    assign_conductor.SetValue(down_cond[line_type_id], line_type_id)
                # Else, then use downstream
                else:
                    changed_cond_dict['SECTION'] = assign_conductor.SectionID
                    changed_cond_dict['OLD'] = assign_conductor.GetValue(line_type_id)
                    changed_cond_dict['NEW'] = down_cond[line_type_id]
                    changed_dict[str(assign_conductor.SectionID) + ', ' + str(line_type_id)] = changed_cond_dict.copy()
                    assign_conductor.SetValue(down_cond[line_type_id], line_type_id)

    return changed_dict, ir_dict


def cyme_report(output_dict, title, headers):
    """
    Creates Cyme report
    :param output_dict: dictionary of dictionaries to report
    :param title: string of report title
    :param headers: list of strings for header
    :return: None
    """
    # Create Cyme report
    report = cympy.rm.CustomReport(title, headers)

    # Iterate through output dictionary
    for output_key, output_line in output_dict.items():
        cyme_row = []
        for header in headers:
            if header == 'SECTION':
                cyme_row.append(cympy.rm.SectionCell(output_line[header]))
            else:
                cyme_row.append(cympy.rm.StringCell(output_line[header]))
        # Add row to output report
        report.AddRow(cyme_row)

    # Display report
    report.Show()


def fix_cond():

    #################################################################################################
    # Assumptions
    max_depth = 3
    max_kva_diff = 0.1
    default_id_list = ['DEFAULT', 'N/A']
    #################################################################################################

    # Check for multiple circuits, else set circuit name
    if len(cympy.study.ListNetworks()) > 1:
        raise ValueError('Found more than one circuit')
    elif len(cympy.study.ListNetworks()) == 0:
        raise ValueError('No circuit loaded')
    else:
        ckt = cympy.study.ListNetworks()[0]

    # Get conductor dictionary, list of OH conductors, list of UG cables
    conductor_dictionary, oh_list, oh_phase_list, ug_list = get_conductors(ckt, default_id_list)

    # Create changed, input required dictionaries
    changed_dictionary = {}
    input_required_dictionary = {}

    # Iterate through OH conductor list
    for oh_conductor in oh_list:
        line_id = ['LineID']
        # Check if conductor is default
        if check_default_cond(oh_conductor.GetValue(line_id[0]), default_id_list):
            changed_dictionary, input_required_dictionary = \
                assign_cond(oh_conductor, line_id, conductor_dictionary, changed_dictionary, input_required_dictionary,
                            max_depth, max_kva_diff, default_id_list)

    # Iterate through OH phase conductor list
    for oh_phase_conductor in oh_phase_list:
        line_id = ['PhaseConductorIDA', 'PhaseConductorIDB', 'PhaseConductorIDC',
                   'NeutralConductorID1', 'NeutralConductorID2']
        # Check if conductor is default
        if check_default_cond(oh_phase_conductor.GetValue(line_id[0]), default_id_list) or \
                check_default_cond(oh_phase_conductor.GetValue(line_id[1]), default_id_list) or \
                check_default_cond(oh_phase_conductor.GetValue(line_id[2]), default_id_list) or \
                check_default_cond(oh_phase_conductor.GetValue(line_id[3]), default_id_list) or \
                check_default_cond(oh_phase_conductor.GetValue(line_id[4]), default_id_list):
            changed_dictionary, input_required_dictionary = \
                assign_cond(oh_phase_conductor, line_id, conductor_dictionary,
                            changed_dictionary, input_required_dictionary, max_depth, max_kva_diff, default_id_list)

    # Iterate through UG conductor list
    for ug_cable in ug_list:
        line_id = ['CableID']
        # Check if conductor is default
        if check_default_cond(ug_cable.GetValue(line_id[0]), default_id_list):
            changed_dictionary, input_required_dictionary = \
                assign_cond(ug_cable, line_id, conductor_dictionary, changed_dictionary, input_required_dictionary,
                            max_depth, max_kva_diff, default_id_list)

    # Initialize final default dictionary
    default_dictionary = {}

    # Go through input required dictionary (try to fix remaining defaults again)
    for sect, default_cond in input_required_dictionary.items():
        line_id = [default_cond['LINEID']]
        changed_dictionary, default_dictionary = \
            assign_cond(default_cond['COND'], line_id, conductor_dictionary, changed_dictionary, default_dictionary,
                        max_depth, max_kva_diff, default_id_list)

    # Create Cyme reports
    cyme_report(changed_dictionary, 'Changed Conductors', ['SECTION', 'OLD', 'NEW', 'LINEID'])
    cyme_report(default_dictionary, 'Input Required Conductors', ['SECTION', 'UPSTREAM', 'DOWNSTREAM', 'LINEID'])


if __name__ == "__main__":
    fix_cond()
