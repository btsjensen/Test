def create_generator(con, cur):
    """
    Add generators to circuit
    :param con: Oracle connection to CMATE Apex
    :param cur: Oracle cursor to CMATE Apex
    :return: None
    """
    import pandas as pd
    import numpy as np
    import cympy

    cur.execute('SELECT * FROM GENERATORS WHERE ADDED IS NULL AND ERRORMESSAGE IS NULL')
    gen_data = pd.DataFrame(cur.fetchall(), columns=[column[0] for column in cur.description])
    gen_data.replace(np.nan, '', inplace=True)

    # Empty lists to extract EquipmentIDs from created Equipment object lists
    ecg_eqids = []
    ecg_eqs = cympy.eq.ListEquipments(cympy.enums.EquipmentType.ElectronicConverterGenerator)
    for ecg_eq in ecg_eqs:
        ecg_eqids.append(ecg_eq.ID)
    sync_eqids = []
    sync_eqs = cympy.eq.ListEquipments(cympy.enums.EquipmentType.SynchronousGenerator)
    for sync_eq in sync_eqs:
        sync_eqids.append(sync_eq.ID)
    ind_eqids = []
    ind_eqs = cympy.eq.ListEquipments(cympy.enums.EquipmentType.InductionGenerator)
    for ind_eq in ind_eqs:
        ind_eqids.append(ind_eq.ID)
    # Dictionary of generator lists to be used for Equipment IDs
    gen_eqids = {'ECG': ecg_eqids, 'SYNCHGEN': sync_eqids, 'INDUCTGEN': ind_eqids}
    # Grab device types, number of generators in network to use as index for section/device name
    gen_number = len(cympy.study.ListDevices(cympy.enums.DeviceType.ElectronicConverterGenerator)) + \
        len(cympy.study.ListDevices(cympy.enums.DeviceType.SynchronousGenerator)) + \
        len(cympy.study.ListDevices(cympy.enums.DeviceType.InductionGenerator))
    # Iterate through data frame to collect generator information
    for i, row in gen_data.iterrows():
        try:
            # Perform checks on input data
            # If Generator Type not equal to 'ECG', 'INDUCTION', or 'SYNCHRONOUS'
            if (row['GENERATORTYPE'] != 'ECG') and (row['GENERATORTYPE'] != 'INDUCTION') and \
                    (row['GENERATORTYPE'] != 'SYNCHRONOUS'):
                gen_data.at[i, 'ERRORMESSAGE'] = 'Incorrect generator type.'
                continue
            # Check if value for node is empty
            if row['NODE'] == '':
                gen_data.at[i, 'ERRORMESSAGE'] = 'Missing node.'
                continue
            # Check if node is in the circuit, if not then just go to next gen (will try on another circuit)
            node = cympy.study.GetNode(row['NODE'])
            if node is None:
                continue
            # Compare Cyme and data frame voltages, row skipped if they do not match
            node_voltage = float(cympy.study.QueryInfoNode('KVLLBase', row['NODE']))
            if node_voltage != row['RATEDKVLL']:
                gen_data.at[i, 'ERRORMESSAGE'] = 'Node voltage incorrect.'
                continue
            # Check active generation
            if row['ACTIVEGENERATION'] == '':
                gen_data.at[i, 'ERRORMESSAGE'] = 'Missing active generation.'
                continue

            # If induction generator, check for power factor, ensure it's between 0 and 100
            if row['GENERATORTYPE'] == 'INDUCTION':
                if (row['POWERFACTOR'] == '') or (int(row['POWERFACTOR'] < 0)) or (int(row['POWERFACTOR']) > 100):
                    gen_data.at[i, 'ERRORMESSAGE'] = 'Incorrect power factor.'
                    continue

            # If synchronous generator, check control type for fixed or voltage
            if row['GENERATORTYPE'] == 'SYNCHRONOUS':
                if (row['CONTROLTYPE'] != 'Fixed_Generation') and (row['CONTROLTYPE'] != 'Voltage_Controlled'):
                    gen_data.at[i, 'ERRORMESSAGE'] = 'Incorrect control type.'
                    continue
                else:
                    if row['CONTROLTYPE'] == 'Fixed_Generation':
                        if (row['POWERFACTOR'] == '') or (int(row['POWERFACTOR'] < 0)) or (
                                int(row['POWERFACTOR']) > 100):
                            gen_data.at[i, 'ERRORMESSAGE'] = 'Incorrect power factor.'
                            continue
                    else:
                        if (row['MAXREACTANCE'] == '') or (row['MINREACTANCE'] == '') or \
                                (int(row['MAXREACTANCE']) < int(row['MINREACTANCE'])):
                            gen_data.at[i, 'ERRORMESSAGE'] = 'Incorrect min/max reactance.'
                            continue

            # Check to see if generator already added
            if row['ADDED'] == '':
                gen_data.at[i, 'ADDED'] = 1
            # Else (generator already added), skip
            else:
                gen_data.at[i, 'ERRORMESSAGE'] = 'Generator already added.'
                continue

            # Assign variables for Electronic Converter Generators
            if 'ELECTRONIC' in str.upper(row['GENERATORTYPE']) or 'ECG' in str.upper(row['GENERATORTYPE']):
                gen_type = cympy.enums.EquipmentType.ElectronicConverterGenerator
                device_type = cympy.enums.DeviceType.ElectronicConverterGenerator
                keyword = 'ECG'
            # Assign variables for Synchronous Generators
            elif 'SYNC' in str.upper(row['GENERATORTYPE']):
                gen_type = cympy.enums.EquipmentType.SynchronousGenerator
                device_type = cympy.enums.DeviceType.SynchronousGenerator
                keyword = 'SYNCHGEN'
            # Assign variables for Induction Generators
            elif 'IND' in str.upper(row['GENERATORTYPE']):
                gen_type = cympy.enums.EquipmentType.InductionGenerator
                device_type = cympy.enums.DeviceType.InductionGenerator
                keyword = 'INDUCTGEN'
            # Else (unexpected generator type), skip
            else:
                gen_data.at[i, 'ERRORMESSAGE'] = 'Generation type unknown.'
                continue

            # Increment number of Generators in circuit for each iteration
            gen_number += 1
            # Define Section and Device variables to use in naming conventions
            section_id = row['NODE'] + '_GEN-' + str(gen_number)
            # Grab Network ID  from each individual node
            circuit_name = cympy.study.QueryInfoNode('NetworkId', row['NODE'])
            # Grab data frame node to acquire coordinates for to node function to add section
            to_node = cympy.study.Node()
            to_node.ID = circuit_name + '_' + str(row['NODE']) + '_GEN-' + str(gen_number)
            to_node.X = node.X + 10
            to_node.Y = node.Y + 20
            # Add section containing generator to node listed on data frame
            cympy.study.AddSection(section_id, circuit_name, section_id, device_type, row['NODE'], to_node)

            # Assign Equipment ID variable based on type of Generator and voltage
            eqid = keyword + '_' + str(node_voltage) + 'KV'
            # If EquipmentID not in list of equipment, add to list, create EquipmentID, and assign values to properties
            if eqid not in gen_eqids[keyword]:
                gen_eqids[keyword].append(eqid)
                cympy.eq.Add(keyword + '_' + str(node_voltage) + 'KV', gen_type)
                # Change EquipmentID properties for apparent power, voltage, and power factor
                cympy.eq.SetValue(1000, 'RatedKVA', eqid, gen_type)
                cympy.eq.SetValue(node_voltage, 'RatedKVLL', eqid, gen_type)
                cympy.eq.SetValue(100, 'PFPercent', eqid, gen_type)
                # If generator is ECG type, change Active generation value
                if keyword is 'ECG':
                    cympy.eq.SetValue(1000, 'ActiveGeneration', eqid, gen_type)
                # If generator is Induction type, changge Active Generation value. Different ID than ECG
                elif keyword is 'INDUCTGEN':
                    cympy.eq.SetValue(1000, 'ActiveGenerationKW', eqid, gen_type)
                # Note: Active Generation for Synchronous Generators does not need to be assigned on EquipmentID
                # because will be set with kVA and power factor

            # Assign equipment ID to device if already exists
            cympy.study.SetValueDevice(eqid, 'DeviceID', section_id, device_type)
            # Assign Active Generation value per device based on data frame
            cympy.study.SetValueDevice(row['ACTIVEGENERATION'], 'GenerationModels[0].ActiveGeneration',
                                       section_id, device_type)
            # If ECG type, change Inverter ratings for KVA, KW, KVAR, and Inverter Control PowerFactor to 100%
            if keyword is 'ECG':
                cympy.study.SetValueDevice(1000, 'Inverter.ConverterRating', section_id, device_type)
                cympy.study.SetValueDevice(1000, 'Inverter.ActivePowerRating', section_id, device_type)
                cympy.study.SetValueDevice(1000, 'Inverter.ReactivePowerRating', section_id, device_type)
                generator = cympy.study.GetDevice(section_id, device_type)
                generator.Execute('Inverter.InverterControls[0].SetType(ConverterControlVoltVarVV11)')
                generator.Execute('Inverter.InverterControls[0].SetType(ConverterControlPowerFactor)')
            # If Synchronous Generator, change Desired Voltage per device based on data frame voltage
            elif keyword is 'SYNCHGEN':
                if 'VOLTAGE' in str.upper(row['CONTROLTYPE']):
                    cympy.study.SetValueDevice('VoltageControl_VoltageControlled', 'VoltageControlType',
                                               section_id, device_type)
                    cympy.study.SetValueDevice(row['RATEDKVLL'], 'KVSet', section_id, device_type)
                    # Change minimum and maximum reactance of defaulted Voltage Controlled type
                    cympy.study.SetValueDevice(row['MAXREACTANCE'], 'GenerationModels[0].MaxReactivePower',
                                               section_id, device_type)
                    cympy.study.SetValueDevice(row['MINREACTANCE'], 'GenerationModels[0].MinReactivePower',
                                               section_id, device_type)
                # Change Power Factor parameter if generator is listed as Fixed Control type in data frame
                elif 'FIXED' in str.upper(row['CONTROLTYPE']):
                    cympy.study.SetValueDevice('VoltageControl_Fixed', 'VoltageControlType', section_id, device_type)
                    cympy.study.SetValueDevice(row['POWERFACTOR'], 'GenerationModels[0].PowerFactor',
                                               section_id, device_type)
            # If Induction Generator, change Power Factor
            elif keyword is 'INDUCTGEN':
                cympy.study.SetValueDevice(row['POWERFACTOR'], 'GenerationModels[0].PowerFactor',
                                           section_id, device_type)

        except cympy.err.CymError as e:
            print(e.GetMessage())

    # Write table to SQL
    table_name = 'GENERATORS'
    column_names = gen_data.columns
    gen_data = gen_data.astype(str)
    insert_data = gen_data.values.tolist()
    del gen_data

    # Clear existing results in table for given circuit
    sql = 'DELETE FROM ' + table_name + ' WHERE ADDED IS NULL AND ERRORMESSAGE IS NULL'
    cur.execute(sql)
    con.commit()

    # Insert new results
    sql = 'INSERT INTO ' + table_name + ' (' + ', '.join(column_names) + ') VALUES ('
    for col_number in range(1, len(column_names) + 1):
        if col_number != 1:
            sql += ', '
        sql += ':' + str(col_number)
    sql += ')'

    cur.prepare(sql)
    cur.executemany(None, insert_data)
    con.commit()
    return None


if __name__ == "__main__":
    import SupportFunctions as Support
    cmate_con, cmate_cur = Support.oracle_conn('CMATE')
    create_generator(cmate_con, cmate_cur)
    cmate_cur.close()
    cmate_con.close()
