import numpy as np
from openmdao.api import ExplicitComponent
from openmdao.api import Group


class PowerSplit(ExplicitComponent):
    """The power split module can split shaft power (from source to two sinks) or electrical load (from sink to two sources)
    'rule'='fixed' will assign a fixed load (absolute terms) to output A and the remainder of power to output B. 
    'rule'='fraction' will assign a fraction of the load to output A. 
    
    Inputs: power_in, power_rating [power_split_fraction or _amount]
    Outputs: power_out_A and _B, heat_out, component_cost, component_weight, component_sizing_margin
    Metadata: rule, efficiency, weight_inc, weight_base, cost_inc, cost_base
    
    Weights in kg/W, cost in USD/W
    """
    def initialize(self):
        #define control rules
        self.options.declare('num_nodes', default=1, desc='Number of flight/control conditions')
        self.options.declare('rule',default='fraction', desc='Control strategy - fraction or fixed power')

        #define technology factors
        self.options.declare('efficiency', default=1., desc='Efficiency (dimensionless)')
        self.options.declare('weight_inc', default=0., desc='kg per input watt')
        self.options.declare('weight_base', default=0., desc='kg base weight')
        self.options.declare('cost_inc', default=0., desc='$ cost per input watt')
        self.options.declare('cost_base', default=0., desc= '$ cost base')

    def setup(self):
        nn = self.options['num_nodes']
        self.add_input('power_in', units='W', desc='Input shaft power or incoming electrical load',shape=(nn,))
        self.add_input('power_rating', val=99999999, units='W', desc='Split mechanism power rating')

        rule = self.options['rule']
        if rule == 'fraction':
            self.add_input('power_split_fraction', val=0.5, desc='Fraction of power to output A',shape=(nn,))
        elif rule == 'fixed':
            self.add_input('power_split_amount', units='W', desc='Raw amount of power to output A',shape=(nn,))
        else:
            msg = 'Specify either "fraction" or "fixed" as power split control rule'
            raise ValueError(msg)



        #outputs and partials
        eta = self.options['efficiency']
        weight_inc = self.options['weight_inc']
        weight_base = self.options['weight_base']
        cost_inc = self.options['cost_inc']
        cost_base = self.options['cost_base']

        self.add_output('power_out_A', units='W', desc='Output power or load to A',shape=(nn,))
        self.add_output('power_out_B', units='W', desc='Output power or load to B',shape=(nn,))
        self.add_output('heat_out', units='W', desc='Waste heat out',shape=(nn,))
        self.add_output('component_cost', units='USD', desc='Splitter component cost')
        self.add_output('component_weight', units='kg', desc='Splitter component weight')
        self.add_output('component_sizing_margin', desc='Fraction of rated power',shape=(nn,))

        if rule == 'fraction':
            self.declare_partials(['power_out_A','power_out_B'],['power_in','power_split_fraction'],rows=range(nn),cols=range(nn))
        elif rule == 'fixed':
            self.declare_partials(['power_out_A','power_out_B'],['power_in','power_split_amount'],rows=range(nn),cols=range(nn))
        self.declare_partials('heat_out', 'power_in', val=(1-eta)*np.ones(nn),rows=range(nn),cols=range(nn))
        self.declare_partials('component_cost','power_rating', val=cost_inc)
        self.declare_partials('component_weight','power_rating', val=weight_inc)
        self.declare_partials('component_sizing_margin','power_in',rows=range(nn),cols=range(nn))
        self.declare_partials('component_sizing_margin','power_rating')



            
    def compute(self, inputs, outputs):
        nn = self.options['num_nodes']
        rule = self.options['rule']
        eta = self.options['efficiency']
        weight_inc = self.options['weight_inc']
        weight_base = self.options['weight_base']
        cost_inc = self.options['cost_inc']
        cost_base = self.options['cost_base']

        if rule == 'fraction':
            outputs['power_out_A'] = inputs['power_in'] * inputs['power_split_fraction'] * eta
            outputs['power_out_B'] = inputs['power_in'] * (1 - inputs['power_split_fraction']) * eta
        elif rule == 'fixed':
            #check to make sure enough power is available
            #if inputs['power_in'] < inputs['power_split_amount']:
            not_enough_idx = np.where(inputs['power_in'] < inputs['power_split_amount'])
            po_A = np.zeros(nn)
            po_B = np.zeros(nn)
            po_A[not_enough_idx] = inputs['power_in'][not_enough_idx] * eta
            po_B[not_enough_idx] = np.zeros(nn)[not_enough_idx]
            #else:
            enough_idx = np.where(inputs['power_in'] >= inputs['power_split_amount'])
            po_A[enough_idx] = inputs['power_split_amount'][enough_idx] * eta
            po_B[enough_idx] = (inputs['power_in'][enough_idx] - inputs['power_split_amount'][enough_idx]) * eta
            outputs['power_out_A'] = po_A
            outputs['power_out_B'] = po_B
        outputs['heat_out'] = inputs['power_in'] * (1 - eta)
        outputs['component_cost'] = inputs['power_rating'] * cost_inc + cost_base
        outputs['component_weight'] = inputs['power_rating'] * weight_inc + weight_base
        outputs['component_sizing_margin'] = inputs['power_in'] / inputs['power_rating']
        
    def compute_partials(self, inputs, J):
        nn = self.options['num_nodes']
        rule = self.options['rule']
        eta = self.options['efficiency']
        if rule == 'fraction':
            J['power_out_A','power_in'] = inputs['power_split_fraction'] * eta
            J['power_out_A','power_split_fraction'] = inputs['power_in'] * eta
            J['power_out_B', 'power_in'] = (1 - inputs['power_split_fraction']) * eta
            J['power_out_B','power_split_fraction'] = -inputs['power_in'] * eta
        elif rule == 'fixed':
            not_enough_idx = np.where(inputs['power_in'] < inputs['power_split_amount'])
            enough_idx = np.where(inputs['power_in'] >= inputs['power_split_amount'])
            #if inputs['power_in'] < inputs['power_split_amount']:
            Jpo_A_pi = np.zeros(nn)
            Jpo_A_ps = np.zeros(nn)
            Jpo_B_pi = np.zeros(nn)
            Jpo_B_ps = np.zeros(nn)
            Jpo_A_pi[not_enough_idx] = eta*np.ones(nn)[not_enough_idx]
            Jpo_A_ps[not_enough_idx] = np.zeros(nn)[not_enough_idx]
            Jpo_B_pi[not_enough_idx] = np.zeros(nn)[not_enough_idx]
            Jpo_B_ps[not_enough_idx] = np.zeros(nn)[not_enough_idx]
            #else:
            Jpo_A_ps[enough_idx] = eta*np.ones(nn)[enough_idx]
            Jpo_A_pi[enough_idx] = np.zeros(nn)[enough_idx]
            Jpo_B_ps[enough_idx] = -eta*np.ones(nn)[enough_idx]
            Jpo_B_pi[enough_idx] = eta*np.ones(nn)[enough_idx]
            J['power_out_A','power_in'] = Jpo_A_pi
            J['power_out_A','power_split_amount'] = Jpo_A_ps
            J['power_out_B','power_in'] = Jpo_B_pi
            J['power_out_B','power_split_amount'] = Jpo_B_ps
        J['component_sizing_margin','power_in'] = 1 / inputs['power_rating']
        J['component_sizing_margin','power_rating'] = - inputs['power_in'] / inputs['power_rating'] ** 2


if __name__ == "__main__":
    from openmdao.api import IndepVarComp, Problem
    prob = Problem()
    prob.model = Group()
    prob.model.add_subsystem('P_in',IndepVarComp('P_i',val=100.,units='kW'))
    prob.model.add_subsystem('P_rated',IndepVarComp('P_r',val=150.,units='kW'))
    prob.model.add_subsystem('control',IndepVarComp('split_ctrl', val=0.7, ))
    prob.model.add_subsystem('splitter',PowerSplit(rule='fraction',efficiency=0.98,weight_inc=0.2,weight_base=20,cost_inc=0.05,cost_base=10000.))
    prob.model.connect('P_in.P_i','splitter.power_in')
    prob.model.connect('P_rated.P_r','splitter.power_rating')
    prob.model.connect('control.split_ctrl','splitter.power_split_fraction')
    prob.setup()
    prob.run_model()
    print(prob['splitter.power_out_A'])
    print(prob['splitter.power_out_B'])
    data = prob.check_partials()
    
