import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="NK 세포 스크리닝 데이터 정규화 툴", layout="wide")

st.title("🧪 NK 세포 스크리닝 데이터 자동 정규화 툴")
st.write("플레이트 Readout 엑셀/CSV 파일을 업로드하면 설정된 플레이트 맵에 따라 정규화를 수행합니다. (A행과 P행은 자동으로 제외됩니다.)")

# 1. 사이드바 및 입력창 설정
st.sidebar.header("📋 실험 정보 입력")
uploaded_file = st.sidebar.file_uploader("엑셀/CSV 파일 업로드", type=["xlsx", "csv"])

nk_top = st.sidebar.text_input("위쪽 절반 NK 세포 이름 (Row B~H)", "NK_Top")
nk_bottom = st.sidebar.text_input("아래쪽 절반 NK 세포 이름 (Row I~O)", "NK_Bottom")

st.sidebar.subheader("⚙️ E:T Ratio 방향 설정")
st.sidebar.caption("위쪽(B행부터)과 아래쪽(I행부터)의 실험 순서에 맞춰 7개의 값을 입력하세요.")

et_input_top = st.sidebar.text_input("🔼 위쪽 절반 E:T Ratio (Row B부터 순서대로)", "80, 40, 20, 10, 5, 2.5, 0")
et_input_bottom = st.sidebar.text_input("🔽 아래쪽 절반 E:T Ratio (Row I부터 순서대로)", "0, 2.5, 5, 10, 20, 40, 80")

et_ratios_top = [float(x.strip()) for x in et_input_top.split(",")]
et_ratios_bottom = [float(x.strip()) for x in et_input_bottom.split(",")]

st.sidebar.subheader("⚙️ 플레이트 맵 설정")
default_mapping = """SNU2491: 3,4,5
SNU324: 7,8,9
MIAPaCa2: 11,12,13
PANC1: 15,16,17
BME: 19,20,21"""
mapping_text = st.sidebar.text_area("암세포별 플레이트 열(Column 1~24) 매핑", default_mapping, height=150)

# 암세포 매핑 파싱
cancer_cells = {}
try:
    for line in mapping_text.strip().split("\n"):
        if ":" in line:
            cell_name, cols_str = line.split(":")
            cols = [int(x.strip()) for x in cols_str.split(",")]
            cancer_cells[cell_name.strip()] = cols
except Exception as e:
    st.error("암세포 열 매핑 입력 형식이 올바르지 않습니다.")

# 데이터 처리 함수
def process_nk_data(data_block, et_list, cell_map):
    rows_list = []
    # 1. 반복구 데이터를 개별적으로 저장
    for r_idx, et in enumerate(et_list):
        for cell_name, cols in cell_map.items():
            for rep_idx, col in enumerate(cols):
                val = data_block[r_idx, col - 1] # 0-based 인덱스
                rows_list.append({
                    "ET_Ratio": et,
                    "Cancer_Cell": cell_name,
                    "Replicate": rep_idx + 1,
                    "Value": val
                })
    df = pd.DataFrame(rows_list)
    
    # 2. ET_Ratio가 0인 3반복 데이터의 "평균" 구하기
    df_et_0 = df[df["ET_Ratio"] == 0.0]
    et_0_means = df_et_0.groupby("Cancer_Cell")["Value"].mean().to_dict()
    
    # 3. 개별 데이터를 ET_Ratio 0 평균값으로 나누어 정규화
    df["Normalized_Value"] = df.apply(
        lambda row: row["Value"] / et_0_means[row["Cancer_Cell"]] if et_0_means.get(row["Cancer_Cell"], 0) != 0 else np.nan, 
        axis=1
    )
    
    # 4. 반복구별 이름 생성 (예: SNU2491_1)
    df["Col_Name"] = df["Cancer_Cell"] + "_" + df["Replicate"].astype(str)
    
    # 5. 피벗 테이블 생성 (평균 내지 않고 개별 나열)
    df_pivot = df.pivot_table(
        index="ET_Ratio", 
        columns="Col_Name", 
        values="Normalized_Value", 
        aggfunc="first"
    )
    
    # 6. 보기 좋게 열 순서 정렬
    col_order = []
    for cell in cell_map.keys():
        for rep_idx in range(len(cell_map[cell])):
            col_order.append(f"{cell}_{rep_idx + 1}")
    
    col_order = [c for c in col_order if c in df_pivot.columns]
    df_pivot = df_pivot[col_order]
    
    # 7. ET Ratio 큰 값에서 작은 값 순으로 (내림차순) 정렬하여 통일감 부여
    df_pivot = df_pivot.sort_index(ascending=False)
    return df_pivot


# 메인 실행 로직
if uploaded_file is not None:
    num_et_top = len(et_ratios_top)
    num_et_bottom = len(et_ratios_bottom)
    
    if num_et_top > 7 or num_et_bottom > 7:
        st.error("A행과 P행을 제외하므로 E:T Ratio는 위/아래 각각 최대 7개까지만 입력 가능합니다.")
    else:
        try:
            # 엑셀/CSV 파일 읽기
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file, header=None)
            else:
                df_raw = pd.read_excel(uploaded_file, header=None)
            
            # 'A'행 위치 자동 탐색
            row_labels = df_raw.iloc[:, 1].astype(str).str.strip()
            a_row_indices = row_labels[row_labels == 'A'].index
            
            if len(a_row_indices) > 0:
                start_idx = a_row_indices[0]
            else:
                start_idx = 33 
            
            # A~P행까지 전체 16행 추출
            plate_data = df_raw.iloc[start_idx:start_idx+16, 2:26].to_numpy(dtype=float)
            
            # ✨수정 포인트: A행(인덱스 0)과 P행(인덱스 15) 건너뛰기
            # 위쪽은 인덱스 1(B행)부터 7줄, 아래쪽은 인덱스 8(I행)부터 7줄 가져오기
            top_block = plate_data[1 : 1+num_et_top, :]         
            bottom_block = plate_data[8 : 8+num_et_bottom, :]   
            
            # 데이터 분석 수행
            df_top_res = process_nk_data(top_block, et_ratios_top, cancer_cells)
            df_bottom_res = process_nk_data(bottom_block, et_ratios_bottom, cancer_cells)
            
            # 화면 출력
            st.subheader(f"📊 {nk_top} 분석 결과 (위쪽 절반, Row B~H)")
            st.dataframe(df_top_res.style.format("{:.4f}"))
            
            st.subheader(f"📊 {nk_bottom} 분석 결과 (아래쪽 절반, Row I~O)")
            st.dataframe(df_bottom_res.style.format("{:.4f}"))
            
            # 엑셀 다운로드 파일 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_top_res.to_excel(writer, sheet_name=nk_top)
                df_bottom_res.to_excel(writer, sheet_name=nk_bottom)
            processed_data = output.getvalue()
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("💾 결과 다운로드")
            st.sidebar.download_button(
                label="정리된 엑셀 파일 다운로드",
                data=processed_data,
                file_name="NK_Screening_Normalized_Result.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("🎉 데이터 정규화가 성공적으로 완료되었습니다!")
            
        except Exception as e:
            st.error(f"데이터 처리 중 오류가 발생했습니다. 오차 원인: {e}")
else:
    st.info("왼쪽 사이드바에서 파일을 업로드해주세요.")
