#!/usr/bin/env python3
"""
Example demonstration of the hold state API.

This script shows how to use the new hold state layer to persistently
hold buttons and sticks without needing to re-specify them in every frame.
"""

import time
import sys
import os

# Add nxbt to path if running from this directory
sys.path.insert(0, '/opt/nxbt/src/nxbt')
import nxbt


def example_hold_buttons():
    """Example 1: Holding buttons persistently"""
    print("Example 1: Holding buttons")
    print("-" * 50)
    
    nx = nxbt.Nxbt()
    idx = nx.create_controller(nxbt.PRO_CONTROLLER)
    nx.wait_for_connection(idx)
    
    print("Starting to hold X button...")
    # 1) Start holding X
    nx.hold_buttons(idx, ["x"])
    
    try:
        print("Sending frames with X held for 5 seconds...")
        start = time.time()
        while time.time() - start < 5.0:
            # Create a fresh packet
            packet = nx.create_input_packet()
            
            # Apply any persistent holds (X in this case)
            packet = nx.apply_hold_state(idx, packet)
            
            # You can also set other momentary things here if you want
            # e.g. packet["DPAD_UP"] = True
            
            # Send the packet for this frame
            nx.set_controller_input(idx, packet)
            
            # Match Pro Controller rate (~120Hz)
            time.sleep(1 / 120.0)
        
        print("Releasing X button...")
        # 2) When you're ready to stop holding X:
        nx.release_buttons(idx, ["x"])
        
        # Continue sending frames for a bit without X held
        print("Sending frames without X held for 2 seconds...")
        start = time.time()
        while time.time() - start < 2.0:
            packet = nx.create_input_packet()
            packet = nx.apply_hold_state(idx, packet)
            nx.set_controller_input(idx, packet)
            time.sleep(1 / 120.0)
            
    except KeyboardInterrupt:
        pass
    finally:
        nx.release_buttons(idx)
        print("Done!")


def example_hold_stick():
    """Example 2: Holding stick position"""
    print("\nExample 2: Holding stick position")
    print("-" * 50)
    
    nx = nxbt.Nxbt()
    idx = nx.create_controller(nxbt.PRO_CONTROLLER)
    nx.wait_for_connection(idx)
    
    print("Starting to hold left stick up (0, 100)...")
    # Hold the left stick up
    nx.hold_stick(idx, "L_STICK", 0, 100)
    
    try:
        print("Sending frames with stick held for 5 seconds...")
        start = time.time()
        while time.time() - start < 5.0:
            packet = nx.create_input_packet()
            packet = nx.apply_hold_state(idx, packet)
            nx.set_controller_input(idx, packet)
            time.sleep(1 / 120.0)
        
        print("Changing to down position (0, -100)...")
        # Change to down position
        nx.hold_stick(idx, "L_STICK", 0, -100)
        
        print("Sending frames with new position for 5 seconds...")
        start = time.time()
        while time.time() - start < 5.0:
            packet = nx.create_input_packet()
            packet = nx.apply_hold_state(idx, packet)
            nx.set_controller_input(idx, packet)
            time.sleep(1 / 120.0)
        
        print("Releasing stick...")
        nx.release_stick(idx, "L_STICK")
        
    except KeyboardInterrupt:
        pass
    finally:
        nx.release_stick(idx)
        print("Done!")


def example_combined():
    """Example 3: Combining buttons and sticks"""
    print("\nExample 3: Combined buttons and sticks")
    print("-" * 50)
    
    nx = nxbt.Nxbt()
    idx = nx.create_controller(nxbt.PRO_CONTROLLER)
    nx.wait_for_connection(idx)
    
    print("Holding B button and moving stick right...")
    # Hold B and move stick right
    nx.hold_buttons(idx, ["b"])
    nx.hold_stick(idx, "L_STICK", 100, 0)
    
    try:
        print("Sending combined input for 5 seconds...")
        start = time.time()
        while time.time() - start < 5.0:
            packet = nx.create_input_packet()
            packet = nx.apply_hold_state(idx, packet)
            
            # Can still add momentary inputs
            if (time.time() - start) > 2.5:
                packet["A"] = True  # Press A halfway through
            
            nx.set_controller_input(idx, packet)
            time.sleep(1 / 120.0)
        
        print("Releasing all inputs...")
        nx.release_buttons(idx)
        nx.release_stick(idx)
        
    except KeyboardInterrupt:
        pass
    finally:
        nx.release_buttons(idx)
        nx.release_stick(idx)
        print("Done!")


if __name__ == "__main__":
    print("=" * 50)
    print("NXBT Hold State API Examples")
    print("=" * 50)
    print()
    print("This script demonstrates three examples:")
    print("1. Holding buttons persistently")
    print("2. Holding stick positions")
    print("3. Combining held buttons and sticks")
    print()
    print("Note: This requires a Bluetooth adapter and a Switch")
    print("      in pairing mode.")
    print()
    
    try:
        choice = input("Which example to run? (1/2/3 or 'all'): ").strip()
        
        if choice == "1":
            example_hold_buttons()
        elif choice == "2":
            example_hold_stick()
        elif choice == "3":
            example_combined()
        elif choice.lower() == "all":
            example_hold_buttons()
            example_hold_stick()
            example_combined()
        else:
            print("Invalid choice. Please run with 1, 2, 3, or 'all'")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
