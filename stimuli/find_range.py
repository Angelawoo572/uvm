class Interval:
    def __init__(self, low, high):
        self.low = low
        self.high = high

def intersect_two_intervals(int1, int2):
    # Find the overlapping part of two ranges
    new_low = max(int1.low, int2.low)
    new_high = min(int1.high, int2.high)
    
    if new_low <= new_high:
        return Interval(new_low, new_high)
    return None # No overlap

def subtract_interval(base, exclude):
    # Case 1: Exclude is entirely outside Base
    if exclude.high < base.low or exclude.low > base.high:
        return [base]
    
    results = []
    # Case 2: There is a piece left on the left side
    if exclude.low > base.low:
        results.append(Interval(base.low, exclude.low - 1))
    
    # Case 3: There is a piece left on the right side
    if exclude.high < base.high:
        results.append(Interval(exclude.high + 1, base.high))
        
    return results

def solve_constraints(constraint_list):
    # Start with the full range of the data type (e.g., 32-bit)
    # Or start with the first "inside" constraint as the base
    final_regions = [Interval(0, 0xFFFFFFFF)] 

    for constraint in constraint_list:
        temp_regions = []
        
        if constraint.type == "inside":
            # Intersect every current region with the new allowed ranges
            for region in final_regions:
                for allowed in constraint.ranges:
                    overlap = intersect_two_intervals(region, allowed)
                    if overlap:
                        temp_regions.append(overlap)
        
        elif constraint.type == "exclude" or constraint.type == "NOT inside":
            # Subtract the excluded range from every current region
            # This is where 1 region can split into 2
            for region in final_regions:
                temp_regions.extend(subtract_interval(region, constraint.range))
        
        final_regions = temp_regions

    return final_regions


def main():
    regions = solve_constraints("user_input")
    # if regions == 1 --> bounded lfsr with min range
    # if regions == 2 --> multirange solver 