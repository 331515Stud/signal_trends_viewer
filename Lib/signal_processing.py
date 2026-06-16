import numpy as np

#-------------------------------------------------------------------------------    
def get_period_arr(sig, winlen):
    l = len(sig)
    if winlen > l*3:
        return
    
    corrlist = []
    samp = sig[:winlen]
    limit = l - winlen
    i=0
    while i < limit:
        a = i
        b = a+winlen
        corr = np.correlate(sig[a:b], samp)
        corrlist.append(corr)
        i+=1
      
    
    maxinds = []
    for i in range(len(corrlist)-4):
        #смотрим на точку i+2
        i0 = corrlist[i]
        i1 = corrlist[i+1]
        i2 = corrlist[i+2]
        i3 = corrlist[i+3]
        i4 = corrlist[i+4]
        
        if i0<i2 and i1<=i2 and i2>=i3 and i2>i4:
            maxinds.append(i+2)
    return maxinds
#----------------------------------------------------------------------------------
def get_greq(sig):
    periods = get_period_arr(sig, 500)
    l = len(periods)
    if l>1:
        freq = ((periods[l-1] - periods[0])/l)*50
        return freq
    else:
        return None
#---------------------------------------------------------------------------------- 