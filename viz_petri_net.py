import pm4py

net, initial_marking, final_marking = pm4py.read_pnml(r"C:\Users\LENONVO\Downloads\IM_models_Domestic_Declarations\BPIC_2019_IMf50.pnml")

pm4py.save_vis_petri_net(net, initial_marking, final_marking, r"C:\Users\LENONVO\Downloads\IM_models_Domestic_Declarations\models_images\BPIC_2019_IMf50.png")