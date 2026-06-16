# Парсит строку и выдает булевый массив, размечающий для каких индексов заданы поддиапазоны

import re
#-----------------------------------------------------------------
def pars_cipher_diapasons_to_boolmask(input_string: str, boolmask_len: int):

    blankless = ''.join(input_string.split())
    if len(blankless) == 0:
        return [True]*boolmask_len

    if boolmask_len < 2:
        return []
    
    def in_range(dia, val: int):
        if len(dia) == 1:
            if dia[0] == val:
                return True
        if len(dia) ==2:
            return dia[0] <= val <= dia[1]
        else:
            return False
    
    
    input_string = ''.join(input_string.split())
    diapasons = re.split(r"[,;\/]", input_string)
    dia_list=[]
    boolmask=[False]*boolmask_len

    for d in diapasons:
        subdia = re.split(r"[:-]", d)
        if len(subdia)>2:
            subdia=subdia[:2]

        if all(x.isdigit() for x in subdia):
            subdia = list(map(int, subdia))

            sorted_tuple_asc = tuple(sorted(subdia))
            dia_list.append(tuple(sorted_tuple_asc))
    
    for i in range(boolmask_len):
        for j in dia_list:
            if in_range(j, i):
                boolmask[i] = True
                continue
            
    return boolmask
#-----------------------------------------------------------------
def rangeTextParse(text: str) ->tuple:
    #возвращает спарсенный из текста диапазон в кортеже
    #если текст пустой - возвращает (-1, -1)
    #если текст не полный - возвращает (-2, -2)
    
    blankless = ''.join(text.split())
    if len(blankless) == 0:
        return (-1, -1)
    
    range = re.split(r"[,:-]", blankless)
    if len(range)>2:
        range=range[:2]

    if all(x.isdigit() for x in range):
        range = list(map(int, range))
    sorted_tuple_asc = tuple(sorted(range))

    if len(sorted_tuple_asc) == 2 and all(type(x) == int for x in sorted_tuple_asc):
        return sorted_tuple_asc
    
    else:
        return (-2, -2)
#-----------------------------------------------------------------    


