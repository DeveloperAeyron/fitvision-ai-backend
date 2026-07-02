import numpy as np

def verify_joint_angle(joint_a, joint_b, joint_c):
    """Computes vector tracking degrees between three sequential coordinate points."""
    a = np.array(joint_a)
    b = np.array(joint_b)
    c = np.array(joint_c)
    
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    
    if angle > 180.0:
        angle = 360.0 - angle
    return angle