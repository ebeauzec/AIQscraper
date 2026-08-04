import os
import json
import zipfile
import logging
import argparse
import urllib.request
import urllib.parse
from xml.etree import ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
ZIP_FILENAME = 'qual_devices_v3.zip'
XML_FILENAME = 'qual_devices.xml'
OUTPUT_FILENAME = 'dqp_drive_baselines.json'
TOKEN_URL = "https://api.activeiq.netapp.com/v1/tokens/accessToken"
DQP_URL = "https://mysupport.netapp.com/site/downloads/firmware/disk-qualification-package"

def parse_dqp_xml(xml_content):
    """Parses DQP XML content and returns baselines and stats."""
    baselines = {}
    stats = {
        'total_parsed': 0,
        'types': {}
    }
    
    try:
        root = ET.fromstring(xml_content)
        
        for device in root.iter('device'):
            model_elem = device.find('model')
            if model_elem is None or not model_elem.text:
                continue
            
            model = model_elem.text.strip()
            
            # Find firmware revision
            latest_fw = None
            q_fw_elem = device.find('qualifiedFirmwareRevision')
            
            if q_fw_elem is not None and q_fw_elem.text:
                latest_fw = q_fw_elem.text.strip()
            else:
                # Fallback to firmwareRevisions
                fw_revs_elem = device.find('firmwareRevisions')
                if fw_revs_elem is not None:
                    for rev in fw_revs_elem.iter('revision'):
                        if rev.text:
                            latest_fw = rev.text.strip()
                            break
                            
            if not latest_fw:
                continue
                
            baselines[model] = latest_fw
            stats['total_parsed'] += 1
            
            # Extract drive type for stats if present
            type_elem = device.find('type')
            drive_type = type_elem.text.strip() if type_elem is not None and type_elem.text else 'UNKNOWN'
            stats['types'][drive_type] = stats['types'].get(drive_type, 0) + 1
            
    except ET.ParseError as e:
        logger.error(f"Error parsing XML: {e}")
        
    return baselines, stats

def get_dqp_xml_content(data_dir):
    """Extracts XML content from DQP zip or raw XML file."""
    zip_path = os.path.join(data_dir, ZIP_FILENAME)
    xml_path = os.path.join(data_dir, XML_FILENAME)
    
    try:
        if os.path.exists(zip_path):
            logger.info(f"Found {ZIP_FILENAME} in {data_dir}. Extracting...")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                xml_files = [f for f in zf.namelist() if f.endswith('.xml')]
                if not xml_files:
                    logger.error("No XML file found inside the DQP zip.")
                    return None
                
                target_xml = xml_files[0]
                for xf in xml_files:
                    if XML_FILENAME in xf:
                        target_xml = xf
                        break
                        
                with zf.open(target_xml) as f:
                    return f.read()
                    
        elif os.path.exists(xml_path):
            logger.info(f"Found {XML_FILENAME} in {data_dir}.")
            with open(xml_path, 'rb') as f:
                return f.read()
    except Exception as e:
        logger.error(f"Error reading DQP files: {e}")
        
    return None

def load_dqp_drive_baselines(data_dir=None):
    """
    Public API for server.py.
    Looks for DQP files in data_dir, parses them, and returns driveModel -> latestFirmwareVersion mapping.
    Returns {} if no files found or parsing fails.
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
        
    xml_content = get_dqp_xml_content(data_dir)
    if xml_content:
        baselines, _ = parse_dqp_xml(xml_content)
        return baselines
    else:
        logger.warning(f"No DQP file ({ZIP_FILENAME} or {XML_FILENAME}) found in {data_dir}.")
        return {}

def download_dqp(token, data_dir):
    """Downloads the DQP zip file using the provided refresh token."""
    try:
        # Step 1: Exchange refresh token for access token
        logger.info("Exchanging refresh token for access token...")
        token_data = json.dumps({"refresh_token": token}).encode('utf-8')
        token_req = urllib.request.Request(
            TOKEN_URL,
            data=token_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method='POST'
        )
        with urllib.request.urlopen(token_req) as response:
            token_resp = json.loads(response.read().decode('utf-8'))
            access_token = token_resp.get("access_token")
            
        if not access_token:
            logger.error("Failed to obtain access token.")
            return False
            
        # Step 2: Use access token to download DQP zip
        logger.info(f"Downloading DQP zip file from {DQP_URL}...")
        dqp_req = urllib.request.Request(
            DQP_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        with urllib.request.urlopen(dqp_req) as response:
            zip_content = response.read()
            
        # Step 3: Save to data directory
        os.makedirs(data_dir, exist_ok=True)
        zip_path = os.path.join(data_dir, ZIP_FILENAME)
        with open(zip_path, 'wb') as f:
            f.write(zip_content)
            
        logger.info(f"Successfully downloaded DQP to {zip_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error downloading DQP: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="DQP Parser and Auto-Download Tool")
    parser.add_argument('--download', action='store_true', help="Attempt to auto-download DQP")
    parser.add_argument('--token', type=str, help="Refresh token for downloading DQP")
    parser.add_argument('--data-dir', type=str, default=DEFAULT_DATA_DIR, help="Directory to store/find DQP files")
    
    args = parser.parse_args()
    
    if args.download:
        if not args.token:
            logger.error("--token is required when using --download")
            return
        success = download_dqp(args.token, args.data_dir)
        if not success:
            logger.error("Download failed. Proceeding with existing files if any.")
            
    xml_content = get_dqp_xml_content(args.data_dir)
    if not xml_content:
        logger.error(f"No DQP file found in {args.data_dir}. Please place '{ZIP_FILENAME}' or '{XML_FILENAME}' there, or use --download with --token.")
        return
        
    baselines, stats = parse_dqp_xml(xml_content)
    
    logger.info("=== DQP Parsing Statistics ===")
    logger.info(f"Total drives parsed: {stats['total_parsed']}")
    for d_type, count in stats['types'].items():
        logger.info(f"  Drive type '{d_type}': {count}")
        
    # Write output to JSON
    output_path = os.path.join(args.data_dir, OUTPUT_FILENAME)
    try:
        os.makedirs(args.data_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(baselines, f, indent=4)
        logger.info(f"Successfully wrote {len(baselines)} baselines to {output_path}")
    except Exception as e:
        logger.error(f"Error writing to {output_path}: {e}")

if __name__ == "__main__":
    main()
